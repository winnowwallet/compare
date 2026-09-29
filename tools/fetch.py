"""Check out every source at the exact revision in sources.json, under .sources/.
Each is a shallow fetch of one commit; a checkout already at the right commit is left alone.
The revisions in reviewed.json are fetched alongside, without checking them out, so citations
can be read at the revision they were reviewed against."""
import os
import subprocess

from common import CONFIG, REVIEWED, ROOT, source_dir

ENV = {**os.environ, 'GIT_LFS_SKIP_SMUDGE': '1'}  # large media is never measured


def git(*args, cwd, check=True):
    return subprocess.run(['git', *args], cwd=cwd, check=check, capture_output=True, text=True, env=ENV).stdout.strip()


def has_commit(path, rev):
    return subprocess.run(['git', 'cat-file', '-e', f'{rev}^{{commit}}'], cwd=path, capture_output=True).returncode == 0


def init(key, repo):
    path = source_dir(key)
    path.mkdir(parents=True, exist_ok=True)
    if not (path / '.git').exists():
        git('init', '-q', cwd=path)
        git('remote', 'add', 'origin', repo, cwd=path)
    else:
        git('remote', 'set-url', 'origin', repo, cwd=path)
    return path


def fetch(key, spec):
    path = init(key, spec['repo'])
    if git('rev-parse', '-q', '--verify', 'HEAD', cwd=path, check=False) == spec['rev']:
        state = 'present'
    else:
        if not has_commit(path, spec['rev']):
            subprocess.run(['git', 'fetch', '-q', '--depth', '1', 'origin', spec['rev']], cwd=path, check=True, env=ENV)
        subprocess.run(['git', '-c', 'advice.detachedHead=false', 'checkout', '-q', '--force', spec['rev']],
                       cwd=path, check=True, env=ENV)
        if git('rev-parse', 'HEAD', cwd=path) != spec['rev']:
            raise SystemExit(f'{key}: expected {spec["rev"]}')
        state = 'fetched'
    # A source that commits no Cargo.lock is resolved with the one in locks/, made when it was pinned.
    lock = path / 'Cargo.lock'
    if spec.get('lock'):
        lock.write_bytes((ROOT / spec['lock']).read_bytes())
    elif lock.exists() and not git('ls-files', 'Cargo.lock', cwd=path):
        lock.unlink()
    return state


def fetch_reviewed(key, spec):
    """The reviewed revision, for reading citations with `git show`. Not checked out."""
    path = init(key, CONFIG['sources'].get(key, spec)['repo'])
    if not has_commit(path, spec['rev']):
        subprocess.run(['git', 'fetch', '-q', '--depth', '1', spec['repo'], spec['rev']], cwd=path, check=True, env=ENV)
    return path


def main():
    for key, spec in CONFIG['sources'].items():
        print(f'{key:22} {fetch(key, spec)}  {spec["rev"][:12]}')
    for key, spec in REVIEWED['sources'].items():
        fetch_reviewed(key, spec)
    print(f'{len(REVIEWED["sources"])} reviewed revisions available')


if __name__ == '__main__':
    main()
