"""Third-party packages each iPhone app resolves and ships, from its own lockfiles and pinned sources.

SwiftPM: every resolved package. npm: the production closure of package.json `dependencies`.
CocoaPods: trunk pods, separately from pods that are the native half of npm packages.
Kotlin: libraries resolved for the iPhone target from Maven Central's Gradle module metadata.
Rust: `cargo tree` for aarch64-apple-ios at each prebuilt library's pinned source.
Go: modules linked into LND's iOS build (`go list -deps` with LND's own mobile build tags).
Full package lists are written, so a re-run shows exactly what was added or removed."""
import json
import os
import re
import subprocess
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from xml.etree import ElementTree

from common import CONFIG, DATA, ROOT, resolve, source_dir, write_json

MAVEN_MIRRORS = ['https://repo.maven.apache.org/maven2', 'https://maven-central.storage-download.googleapis.com/maven2']
MAVEN_CACHE = ROOT / '.cache/maven'
KOTLIN_RUNTIME = {'org.jetbrains.kotlin:kotlin-stdlib', 'org.jetbrains.kotlin:kotlin-stdlib-common'}


# ── SwiftPM and CocoaPods ─────────────────────────────────────
def spm(ref):
    d = json.loads(resolve(ref).read_text())
    pins = d.get('pins') or d.get('object', {}).get('pins', [])
    return sorted(f"{(p.get('identity') or p['package']).lower()}@{(p.get('state') or {}).get('version') or (p.get('state') or {}).get('revision', '')[:12]}"
                  for p in pins)


def pods(ref):
    text = resolve(ref).read_text()
    trunk = re.search(r'\nSPEC REPOS:\n(.*?)\n\n', text, re.S)
    external = re.search(r'\nEXTERNAL SOURCES:\n(.*?)\n\n', text, re.S)
    ext = re.findall(r'^  "?([^:"\n]+)"?:\n    :path: "?([^"\n]+)"?', external.group(1), re.M) if external else []
    return {
        'trunk': sorted(set(re.findall(r'^    - "?([^"\n]+?)"?$', trunk.group(1), re.M))) if trunk else [],
        'native_half_of_npm_packages': sorted(n for n, p in ext if 'node_modules' in p and 'node_modules/react-native/' not in p),
        'react_native_core': sorted(n for n, p in ext if 'node_modules/react-native/' in p),
        'local': sorted(n for n, p in ext if 'node_modules' not in p),
    }


# ── npm ───────────────────────────────────────────────────────
def yarn_entries(lock):
    entries, entry, section = {}, None, None
    for line in lock.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        if not line.startswith(' '):
            entry = {'deps': {}}
            for k in (k.strip().strip('"') for k in line.rstrip(':').split(', ')):
                entries[k] = entry
            section = None
        elif line.startswith('  version '):
            entry['version'] = line.split('"')[1]
        elif line.strip() in ('dependencies:', 'optionalDependencies:'):
            section = 'deps'
        elif line.startswith('    ') and section:
            name, _, rng = line.strip().partition(' ')
            entry['deps'][name.strip('"')] = rng.strip('"')
        elif line.startswith('  ') and not line.startswith('    '):
            section = None
    return entries


def npm_yarn(spec):
    entries = yarn_entries(resolve(spec['yarn']))
    roots = json.loads(resolve(spec['package']).read_text()).get('dependencies', {})
    seen, todo = set(), list(roots.items())
    while todo:
        name, rng = todo.pop()
        e = entries.get(f'{name}@{rng}') or next((v for k, v in entries.items() if k.startswith(name + '@')), None)
        if e is None or f"{name}@{e.get('version')}" in seen:
            continue
        seen.add(f"{name}@{e.get('version')}")
        todo += list(e['deps'].items())
    return sorted(roots), sorted(seen)


def npm_bun(ref):
    d = json.loads(re.sub(r',(\s*[}\]])', r'\1', resolve(ref).read_text()))  # JSONC trailing commas
    packages, roots = d['packages'], d['workspaces']['']['dependencies']
    seen, todo = set(), [('', n) for n in roots]
    while todo:
        parent, name = todo.pop()
        key = next((k for k in (f'{parent}/{name}' if parent else None, name) if k and k in packages), None)
        if key is None or packages[key][0] in seen:
            continue
        entry = packages[key]
        seen.add(entry[0])
        meta = entry[2] if len(entry) > 2 and isinstance(entry[2], dict) else {}
        for section in ('dependencies', 'optionalDependencies'):
            todo += [(key, dep) for dep in meta.get(section, {})]
    return sorted(roots), sorted(seen)


# ── Kotlin (Maven Central) ────────────────────────────────────
def maven_fetch(path):
    cached = MAVEN_CACHE / path.replace('/', '_')
    if cached.exists():
        return cached.read_text() or None
    MAVEN_CACHE.mkdir(parents=True, exist_ok=True)
    for attempt in range(5):
        missing = 0
        for base in MAVEN_MIRRORS:
            try:
                with urllib.request.urlopen(f'{base}/{path}', timeout=30) as r:
                    text = r.read().decode()
                cached.write_text(text)
                return text
            except urllib.error.HTTPError as e:
                missing += e.code == 404
            except OSError:
                pass
        if missing == len(MAVEN_MIRRORS):
            cached.write_text('')
            return None
        time.sleep(2 ** attempt)
    raise SystemExit(f'Maven Central unreachable for {path}')


def version_key(v):
    return [(0, int(p), '') if p.isdigit() else (1, 0, p) for p in re.split(r'[.-]', v)]


def maven_dependencies(group, module, version, target):
    base = f"{group.replace('.', '/')}/{module}/{version}/{module}-{version}"
    meta = maven_fetch(base + '.module')
    if meta:
        variants = json.loads(meta).get('variants', [])
        ios = [v for v in variants if v.get('attributes', {}).get('org.jetbrains.kotlin.platform.type') == 'native'
               and v['attributes'].get('org.jetbrains.kotlin.native.target') == target]
        ios.sort(key=lambda v: v['attributes'].get('org.gradle.usage') != 'kotlin-api')
        chosen = ios or [v for v in variants if v.get('attributes', {}).get('org.gradle.usage') in ('kotlin-api', 'java-api')]
        if not chosen:
            return None
        variant = chosen[0]
        if 'available-at' in variant:  # the platform variant lives in its own artifact
            at = variant['available-at']
            return [('redirect', at['group'], at['module'], at['version'])]
        return [(d['group'], d['module'], (d.get('version') or {}).get('requires') or (d.get('version') or {}).get('strictly')
                 or (d.get('version') or {}).get('prefers')) for d in variant.get('dependencies', [])]
    pom = maven_fetch(base + '.pom')
    if not pom:
        return None
    ns = {'m': 'http://maven.apache.org/POM/4.0.0'}
    return [(d.findtext('m:groupId', '', ns), d.findtext('m:artifactId', '', ns), d.findtext('m:version', '', ns))
            for d in ElementTree.fromstring(pom).findall('.//m:dependencies/m:dependency', ns)
            if d.findtext('m:scope', 'compile', ns) in ('compile', 'runtime') and d.findtext('m:optional', 'false', ns) != 'true']


def maven(spec):
    """Roots name their versions from the app's Gradle catalog, e.g. {lightningkmp}."""
    versions = tomllib.loads(resolve(spec['catalog']).read_text())['versions']
    chosen, todo = {}, [tuple(r.format(**versions).split(':')) for r in spec['roots']]
    while todo:
        g, m, v = todo.pop()
        key = f'{g}:{m}'
        if key in KOTLIN_RUNTIME or not v or (key in chosen and version_key(chosen[key]) >= version_key(v)):
            continue
        deps = maven_dependencies(g, m, v, spec['target'])
        if deps is None:
            raise SystemExit(f'cannot resolve {key}:{v} for {spec["target"]}')
        chosen[key] = v  # Gradle keeps the highest requested version
        if deps and deps[0][0] == 'redirect':
            todo.append(deps[0][1:])
        else:
            todo += [d for d in deps if d[2]]
    platform = re.compile(r'-(iosarm64|iosx64|iossimulatorarm64)$')
    libraries = sorted({f'{platform.sub("", k)}@{chosen[k]}' for k in chosen if not platform.search(k)} |
                       {f'{platform.sub("", k)}@{chosen[k]}' for k in chosen if platform.search(k) and platform.sub('', k) not in chosen})
    return [lib for lib in libraries if not lib.startswith(spec['engine'] + '@')]


# ── Rust and Go ───────────────────────────────────────────────
def cargo(crate):
    out = subprocess.run(['cargo', 'tree', '--manifest-path', str(source_dir(crate['source']) / 'Cargo.toml'), *crate['args'],
                          '-e', 'normal', '--target', CONFIG['cargo_target'], '--prefix', 'none', '--format', '{p}', '--locked'],
                         capture_output=True, text=True, check=True).stdout
    engine = re.compile(CONFIG['cargo_engine_crates'])
    return sorted({re.sub(r' \(\*\)$', '', l).strip() for l in out.splitlines()
                   if l.strip() and '(/' not in l and not engine.match(l)})


def go_modules(source):
    spec = CONFIG['go']
    # A module replaced by another (a fork's go.mod often does this) is listed as the replacement.
    template = ('{{with .Module}}{{if not .Main}}{{.Path}} {{with .Replace}}{{.Path}}@{{.Version}}'
                '{{else}}{{.Path}}@{{.Version}}{{end}}\n{{end}}{{end}}')
    out = subprocess.run(['go', 'list', '-deps', f'-tags={spec["tags"]}', '-f', template, spec['package']],
                         cwd=source_dir(source), env={**os.environ, **spec['env']},
                         capture_output=True, text=True, check=True).stdout
    return sorted({line.split()[1] for line in out.splitlines() if line.strip() and not line.startswith(spec['first_party'])})


def main():
    go, out = {}, {}
    for wallet, spec in CONFIG['wallets'].items():
        d, r = spec['deps'], {}
        if 'spm' in d:
            r['spm'] = [p for p in spm(d['spm']) if not p.startswith(d.get('spm_engine', '\0') + '@')]
        if 'maven' in d:
            r['kotlin'] = maven(d['maven'])
        if 'cargo' in d:
            per = {c['source']: cargo(c) for c in d['cargo']}
            r['rust'] = sorted(set().union(*per.values()))
            r['rust_copies'] = sum(len(v) for v in per.values())
            r['rust_per_library'] = {k: len(v) for k, v in per.items()}
        if 'go' in d:
            source = d['go']['source']
            r['go'] = go[source] = go.get(source) or go_modules(source)
        if 'npm' in d:
            r['npm_direct'], r['npm'] = npm_yarn(d['npm'])
        if 'bun' in d:
            r['npm_direct'], r['npm'] = npm_bun(d['bun'])
        if 'pods' in d:
            p = pods(d['pods'])
            r['pods'] = p['trunk']
            r['pods_from_npm_and_react_native'] = len(p['native_half_of_npm_packages']) + len(p['react_native_core'])
        r['total'] = sum(len(r[k]) for k in ('spm', 'kotlin', 'rust', 'go', 'npm', 'pods') if k in r)
        out[wallet] = r
        print(wallet, {k: (len(v) if isinstance(v, list) else v) for k, v in r.items() if k != 'rust_per_library'})
    write_json(DATA / 'deps.json', out)


if __name__ == '__main__':
    main()
