"""Test code per wallet: the lines of tests in the wallet's own repository, counted the way the code is.

A file is test code when it is in one of the code languages and is what the line count leaves out as a test:
a test folder (`tests`, `__tests__`, `e2e`, `fuzz`, an Xcode `…Tests` target, a Kotlin `…Test` source set)
or a test file name (`*Tests.swift`, `*.test.ts`, `_test.go`, `test_*.rs` …). Tests for other platforms
(an `android` or `desktop` folder, Android's `androidTest`), vendored, generated and skipped paths are left
out, as they are from the code. A wallet whose tests are named otherwise lists them in sources.json as
`tests` (Winnow's are Lean executables named `…Test.lean`, `…Regtest.lean`, a fuzzer and UI journeys).

Only the wallet's own repositories are read: the ones its `app` and `bitcoin` parts come from. An engine's
tests are the engine's, as its code is."""
import json
import re

from common import (CLOC, CONFIG, DATA, EXTENSIONS, GENERATED, LANGS, ROOT, STAGE, cloc, left_out, resolve,
                    source_dir, write_json)

TEST_DIRS = {'test', 'tests', '__tests__', '__mocks__', 'e2e', 'integration_test', 'itest', 'lntest', 'fuzz',
             'Tests', 'testdata', 'test_utils', 'testutil', 'testutils', 'commonTest', 'jvmTest', 'nativeTest',
             'linuxTest', 'iosTest', 'iosArm64Test', 'iosX64Test', 'iosSimulatorArm64Test', 'appleTest'}
TEST_DIR = re.compile(r'^[A-Za-z]*(Tests|UITests|Test)$')
TEST_NAME = re.compile(r'(_test\.go|\.test\.[jt]sx?|\.spec\.[jt]sx?|Tests?\.(swift|kt|m|mm|lean)|_test\.dart|'
                       r'(^|_)tests?\.rs|^test_[A-Za-z0-9_]*\.rs|_tests?\.rs)$')
# never shipped to an iPhone, so never the iPhone app's tests
OTHER_PLATFORM = {'android', 'androidTest', 'androidUnitTest', 'androidInstrumentedTest', 'androidMain',
                  'desktop', 'jvmMain', 'linuxMain', 'phoenix-android', 'web', 'electron'}
NEVER = {'.git', 'node_modules', 'Pods', '.sources', 'build', 'dist', 'vendor', 'third_party', 'thirdparty'}


def is_test(rel_parts):
    """Whether a path (its parts, file name last) is test code by the rules above."""
    dirs, name = rel_parts[:-1], rel_parts[-1]
    if any(d in OTHER_PLATFORM for d in dirs):
        return False
    if any(d in TEST_DIRS or TEST_DIR.match(d) for d in dirs):
        return True
    return bool(TEST_NAME.search(name))


def own_sources(spec):
    """The repositories the wallet's own parts come from."""
    keys = []
    for part in ('app', 'bitcoin'):
        for ref in spec['code'].get(part, []):
            key = ref.partition(':')[0]
            if key not in keys:
                keys.append(key)
    return keys


def files(spec):
    left = [resolve(s).resolve() for s in left_out(spec)]
    declared = [resolve(r) for r in spec.get('tests', [])]
    found, generated = [], []
    for key in own_sources(spec):
        root = source_dir(key)
        for f in sorted(p for p in root.rglob('*') if p.is_file() and p.suffix in EXTENSIONS):
            parts = f.relative_to(root).parts
            if NEVER & set(parts[:-1]):
                continue
            named = any(d == f or d in f.parents for d in declared)
            if not named and any(s == f.resolve() or s in f.resolve().parents for s in left):
                continue
            if not (named or is_test(parts)):
                continue
            if GENERATED.search(f.read_text(errors='ignore')[:1500]):
                generated.append(f'{key}/{"/".join(parts)}')
                continue
            found.append(f)
    return found, generated


def measure(spec):
    found, generated = files(spec)
    if not found:
        return {'code': 0, 'files': 0, 'languages': {}, 'generated_excluded': generated}
    listing = STAGE.with_name('.tests-list')
    listing.write_text('\n'.join(str(f) for f in found) + '\n')
    try:
        rows = json.loads(cloc(['--json', '--include-lang=' + ','.join(LANGS), '--list-file', str(listing)]) or '{}')
    finally:
        listing.unlink()
    languages = {k: v['code'] for k, v in rows.items() if k not in ('header', 'SUM')}
    return {'code': sum(languages.values()), 'files': len(found), 'languages': dict(sorted(languages.items())),
            'generated_excluded': sorted(generated)}


def main():
    result = {}
    for wallet, spec in CONFIG['wallets'].items():
        result[wallet] = measure(spec)
        print(wallet, result[wallet]['code'], 'lines in', result[wallet]['files'], 'files')
    write_json(DATA / 'tests.json', result)


if __name__ == '__main__':
    main()
