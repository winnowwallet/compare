"""Check out every source at the exact revision in sources.json, under .sources/.
Each is a shallow fetch of one commit; a checkout already at the right commit is left alone."""
import os
import subprocess

from common import CONFIG, ROOT, source_dir


def git(*args, cwd):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def fetch(key, spec):
    path = source_dir(key)
    if (path / '.git').exists() and git('rev-parse', 'HEAD', cwd=path) == spec['rev']:
        return 'present'
    path.mkdir(parents=True, exist_ok=True)
    if not (path / '.git').exists():
        git('init', '-q', cwd=path)
        git('remote', 'add', 'origin', spec['repo'], cwd=path)
    env = {**os.environ, 'GIT_LFS_SKIP_SMUDGE': '1'}  # large media is never measured
    subprocess.run(['git', 'fetch', '-q', '--depth', '1', 'origin', spec['rev']], cwd=path, check=True, env=env)
    subprocess.run(['git', '-c', 'advice.detachedHead=false', 'checkout', '-q', '--force', 'FETCH_HEAD'],
                   cwd=path, check=True, env=env)
    got = git('rev-parse', 'HEAD', cwd=path)
    if got != spec['rev']:
        raise SystemExit(f'{key}: expected {spec["rev"]}, got {got}')
    return 'fetched'


def main():
    for key, spec in CONFIG['sources'].items():
        print(f'{key:22} {fetch(key, spec)}  {spec["rev"][:12]}')
    # Synonym's LDK Node fork commits no Cargo.lock; use the one this measurement was made with.
    for wallet in CONFIG['wallets'].values():
        for crate in wallet['deps'].get('cargo', []):
            if 'lock' in crate:
                (source_dir(crate['source']) / 'Cargo.lock').write_bytes((ROOT / crate['lock']).read_bytes())


if __name__ == '__main__':
    main()
