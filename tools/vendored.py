"""Third-party code committed into each app's repository instead of declared as a dependency,
plus committed binaries and scripts that patch installed dependencies. Android-only paths are ignored.

A copied package is counted by the source that ships (not tests, build scripts or tool configuration); when only its published build output was copied
(a `dist/` directory), that output is counted instead. Build output next to source is not
counted twice, and files marked as generated are skipped."""
import json
import re

from common import CONFIG, DATA, GENERATED, LANGS, cloc, resolve, source_dir, write_json

IGNORE = re.compile(r'/(\.git|node_modules|android|phoenix-android|build|target)(/|$)')
VENDOR_DIR = re.compile(r'^(vendor|vendored|third[_-]?party|thirdparty|external|externals|zeus_modules|Pods)$', re.I)
NOT_A_POD = re.compile(r'^(Headers|Target Support Files|Local Podspecs)$|\.xcodeproj$')  # CocoaPods' own scaffolding, in a committed Pods/
LICENSE = re.compile(r'^(LICEN[CS]E|COPYING)(\.[a-z]+)?$', re.I)
BINARY = re.compile(r'\.(a|so|dylib|dll|wasm|xcframework|framework)$', re.I)
TOOLING = re.compile(r'(^|/)([^/]*\.config\.[cm]?[jt]s|\.?eslintrc[^/]*|babel\.config\.[^/]+)$')  # build and lint configuration
SOURCE_EXT = {'.ts', '.tsx', '.js', '.jsx', '.mjs', '.swift', '.m', '.mm', '.h', '.kt', '.go', '.rs', '.c', '.cc', '.cpp'}


def code_lines(files):
    if not files:
        return 0
    out = cloc(['--csv', '--include-lang=' + ','.join(LANGS), '--list-file=-'], input_text='\n'.join(map(str, files)))
    return sum(int(r.split(',')[4]) for r in out.splitlines() if r and r[0].isdigit() and r.split(',')[1] != 'SUM')


def package_lines(tree):
    files = [tree] if tree.is_file() else sorted(f for f in tree.rglob('*') if f.is_file() and f.suffix in SOURCE_EXT
                                                   and not f.name.endswith('.d.ts') and 'node_modules' not in f.parts)
    files = [f for f in files if not TOOLING.search(f.name) and not GENERATED.search(f.read_text(errors='ignore')[:1500])]
    source = [f for f in files if not {'dist', 'test', 'tests', '__tests__', 'scripts'} & set(f.relative_to(tree).parts[:-1] if tree.is_dir() else ())]
    built = [f for f in files if 'dist' in (f.relative_to(tree).parts[:-1] if tree.is_dir() else ())]
    lines = code_lines(source)
    return (lines, 'source') if lines else (code_lines(built), 'published build output')


def packages_in(vendor_dir):
    """Each copied package: scoped (@scope/name), plain directories, and single files."""
    out = []
    for child in sorted(vendor_dir.iterdir()):
        if vendor_dir.name == 'Pods' and NOT_A_POD.search(child.name):
            continue
        if child.is_dir() and child.name.startswith('@'):
            out += sorted(p for p in child.iterdir() if p.is_dir())
        elif child.is_dir() or child.suffix in SOURCE_EXT:
            out.append(child)
    return out


def scan(root):
    found = {'copied_packages': {}, 'nested_licenses': [], 'binaries': [], 'patches': []}
    vendor_dirs = []  # a vendor directory inside another (Pods/GoogleUtilities/third_party) is already counted by its parent
    for p in sorted(root.rglob('*')):
        rel = '/' + str(p.relative_to(root))
        if IGNORE.search(rel):
            continue
        if p.is_dir() and VENDOR_DIR.match(p.name) and not any(v in p.parents for v in vendor_dirs):
            vendor_dirs.append(p)
            for pkg in packages_in(p):
                lines, counted = package_lines(pkg)
                if lines:
                    found['copied_packages'][str(pkg.relative_to(root))] = {'lines': lines, 'counted': counted}
        elif p.is_file() and LICENSE.match(p.name) and p.parent != root:
            found['nested_licenses'].append(rel)
        if BINARY.search(p.name) and not (p.is_file() and p.suffix == '.jar'):
            found['binaries'].append(rel)
    patches = root / 'patches'
    package = root / 'package.json'
    if patches.is_dir() and package.exists() and 'patches/' in json.loads(package.read_text()).get('scripts', {}).get('postinstall', '') \
            or patches.is_dir() and any(patches.glob('*.patch')):
        found['patches'] = sorted(f.name for f in patches.iterdir() if f.is_file() and f.name != 'index.mjs')
    found['copied_lines'] = sum(v['lines'] for v in found['copied_packages'].values())
    return found


def main():
    out = {wallet: scan(source_dir(spec['app_source'])) for wallet, spec in CONFIG['wallets'].items()}
    for wallet, spec in CONFIG['wallets'].items():  # copies a wallet names itself, such as BlueWallet's blue_modules/pako
        root = source_dir(spec['app_source'])
        for ref in spec.get('vendored', []):
            tree = resolve(ref)
            lines, counted = package_lines(tree)
            out[wallet]['copied_packages'][str(tree.relative_to(root))] = {'lines': lines, 'counted': counted}
        out[wallet]['copied_lines'] = sum(v['lines'] for v in out[wallet]['copied_packages'].values())
    for wallet, f in out.items():
        print(wallet, f['copied_lines'], 'copied lines;', len(f['patches']), 'patch scripts;', len(f['binaries']), 'binaries')
    write_json(DATA / 'vendored.json', out)


if __name__ == '__main__':
    main()
