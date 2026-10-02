"""Move every source to what each wallet ships today, and rewrite sources.json.

Wallet repositories follow their default branch. Every engine and prebuilt library follows the
version its wallet declares, read from the wallet's own files at the new revision: Phoenix's Gradle
catalog, Bitkit's Package.resolved, Zeus's fetch-libraries-versions.json, Blixt's bun.lock through
react-native-turbo-lnd, and LDK Node's Cargo.lock for rust-lightning. Nothing is picked by hand.

A source that commits no Cargo.lock gets one generated when its revision changes, saved in locks/
so the measurement stays reproducible. When anything moved, `snapshot` becomes today's date (UTC)
and a summary of the moves is written to .cache/update.md for the commit message."""
import json
import re
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from common import CONFIG, CONFIG_PATH, ROOT, resolve, source_dir, write_config
from fetch import fetch, git


def remote_rev(repo, ref, required=True):
    """The commit a branch or tag names; annotated tags are peeled."""
    out = subprocess.run(['git', 'ls-remote', repo, ref, f'{ref}^{{}}'], capture_output=True, text=True, check=True).stdout
    refs = {name: sha for sha, name in (line.split('\t') for line in out.splitlines())}
    rev = refs.get(f'{ref}^{{}}') or refs.get(ref)
    if not rev and required:
        raise SystemExit(f'{repo} has no {ref}')
    return rev


def latest_tag(repo, pattern):
    """The tag matching `pattern` (one group: its version) with the highest version, and the commit it names."""
    out = subprocess.run(['git', 'ls-remote', '--tags', repo], capture_output=True, text=True, check=True).stdout
    refs = {name.removeprefix('refs/tags/'): sha for sha, name in (line.split('\t') for line in out.splitlines())}
    found = {}
    for name in refs:
        m = re.fullmatch(pattern, name.removesuffix('^{}'))
        if m:
            found[name.removesuffix('^{}')] = tuple(int(n) for n in m.group(1).split('.'))
    if not found:
        raise SystemExit(f'{repo} has no tag matching {pattern}')
    tag = max(found, key=found.get)
    return tag, refs.get(f'{tag}^{{}}') or refs[tag]  # an annotated tag is peeled to its commit


def first_branch(repo, branches):
    """The first of `branches` that exists, so a working branch can fall back to main once it merges."""
    for branch in [branches] if isinstance(branches, str) else branches:
        rev = remote_rev(repo, branch, required=False)
        if rev:
            return rev
    raise SystemExit(f'{repo} has none of {branches}')


def dig(value, dotted):
    for part in dotted.split('.'):
        value = value[part]
    return value


def spm_pin(text, identity):
    d = json.loads(text)
    for p in d.get('pins') or d['object']['pins']:
        if (p.get('identity') or p.get('package', '')).lower() == identity:
            return p['state']['revision'], p['state'].get('version')
    raise KeyError(identity)


def cargo_version(lock_text, manifest_text, crate):
    """The version of `crate` the root package itself depends on (a lock can hold several)."""
    root = tomllib.loads(manifest_text)['package']['name']
    packages = tomllib.loads(lock_text)['package']
    versions = {p['version'] for p in packages if p['name'] == crate}
    for p in packages:
        if p['name'] == root and 'source' not in p:
            for dep in p.get('dependencies', []):
                name, _, version = dep.partition(' ')
                if name == crate:
                    return version.split(' ')[0] if version else versions.pop()
    raise KeyError(crate)


def bun_version(text, package):
    d = json.loads(re.sub(r',(\s*[}\]])', r'\1', text))  # JSONC trailing commas
    return d['packages'][package][0].rpartition('@')[2]


def properties(text):
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line and not line.lstrip().startswith('#'))


def resolve_rule(key, spec):
    """Returns (repo, rev, version, tag) for a source's `track` rule."""
    rule, repo = spec['track'], spec['repo']
    if 'tag_latest' in rule:  # the wallet's latest release, for one whose branch head is not what ships
        tag, rev = latest_tag(repo, rule['tag_latest'])
        return repo, rev, re.fullmatch(rule['tag_latest'], tag).group(1), tag
    if 'branch' in rule:
        repo = rule.get('repo', repo)  # a rule may move a source to another repository
        return repo, first_branch(repo, rule['branch']), None, None
    ref = rule['from']
    path = resolve(ref)
    if not path.is_file():
        raise SystemExit(f'{key}: {ref} is missing, so the version it pins cannot be read')
    text = path.read_text()
    if 'spm' in rule:
        rev, version = spm_pin(text, rule['spm'])
        return repo, rev, version, None
    if 'properties' in rule:
        props = properties(text)
        repo = rule['properties']['repo'].format(**props)
        return repo, rule['properties']['rev'].format(**props), None, None
    if 'toml' in rule:
        value = dig(tomllib.loads(text), rule['toml'])
    elif 'json' in rule:
        value = dig(json.loads(text), rule['json'])
    elif 'bun' in rule:
        value = bun_version(text, rule['bun'])
    elif 'regex' in rule:
        value = re.search(rule['regex'], text).group(1)
    elif 'cargo' in rule:
        manifest = (path.parent / 'Cargo.toml').read_text()
        value = cargo_version(text, manifest, rule['cargo'])
    else:
        raise SystemExit(f'{key}: unknown track rule {rule}')
    tag = rule['tag'].format(value)
    return repo, remote_rev(repo, f'refs/tags/{tag}'), value.removeprefix('release_').removeprefix('v'), tag


def cargo_sources():
    return {c['source']: c.get('dir', '') for w in CONFIG['wallets'].values() for c in w['deps'].get('cargo', [])}


def ensure_lock(key, spec, moved, below=''):
    """Use the source's own Cargo.lock; generate one only when it commits none."""
    path = source_dir(key)
    if git('ls-files', str(Path(below) / 'Cargo.lock'), cwd=path):
        if spec.pop('lock', None):
            (ROOT / f'locks/{key}.Cargo.lock').unlink(missing_ok=True)
        return
    lock = ROOT / f'locks/{key}.Cargo.lock'
    if moved or not lock.exists():
        (path / below / 'Cargo.lock').unlink(missing_ok=True)
        subprocess.run(['cargo', 'generate-lockfile', '--manifest-path', str(path / below / 'Cargo.toml')], check=True)
        lock.write_bytes((path / below / 'Cargo.lock').read_bytes())
    spec['lock'] = f'locks/{key}.Cargo.lock'
    fetch(key, spec)


def describe(spec):
    repo = spec['repo'].removeprefix('https://github.com/').removesuffix('.git')
    if spec.get('tag'):
        return f'{repo} {spec["tag"]}'
    if spec.get('version') and spec['track'].get('spm'):
        return f'{repo} {spec["version"]}'
    return f'{repo}@{spec["rev"][:7]}' + (f' ({spec["version"]})' if spec.get('version') else '')


def main():
    moves = []
    for key, spec in CONFIG['sources'].items():
        repo, rev, version, tag = resolve_rule(key, spec)
        before = dict(spec)
        spec.update(repo=repo, rev=rev)
        for field, value in (('tag', tag), ('version', version)):
            if value:
                spec[field] = value
            else:
                spec.pop(field, None)
        fetch(key, spec)
        if key in cargo_sources():
            ensure_lock(key, spec, moved=before.get('rev') != rev, below=cargo_sources()[key])
        if spec.get('version_from'):
            m = re.search(spec['version_from']['pattern'], (source_dir(key) / spec['version_from']['path']).read_text())
            spec['version'] = '.'.join(str(int(g)) for g in m.groups())
        spec['label'] = describe(spec)
        spec['date'] = git('log', '-1', '--format=%cs', cwd=source_dir(key))
        if before.get('rev') != rev:
            old = before.get('label') or (before.get('rev') or '')[:7] or 'new'
            moves.append(f'{key}: {old} → {spec["label"]}')
        print(f'{key:22} {spec["label"]}  ({spec["date"]})')
    if moves:
        CONFIG['snapshot'] = datetime.now(timezone.utc).date().isoformat()
    write_config(CONFIG_PATH, CONFIG)
    summary = ROOT / '.cache/update.md'
    summary.parent.mkdir(exist_ok=True)
    summary.write_text(''.join(f'- {m}\n' for m in moves))
    print(f'{len(moves)} sources moved' + ''.join(f'\n  {m}' for m in moves))


if __name__ == '__main__':
    main()
