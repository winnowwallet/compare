"""The rules that move pins and judge how fresh the hand review is. Each case is the shape of a
real file the rule reads: Bitkit's Package.resolved, LDK Node's Cargo.lock, Blixt's bun.lock and
react-native-turbo-lnd's lnd-source.properties."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))

from evidence import find, locate  # noqa: E402
from render import scale  # noqa: E402
import common  # noqa: E402
import update  # noqa: E402
from deps import npm_lock  # noqa: E402
from update import bun_version, cargo_version, properties, spm_pin  # noqa: E402


class Pins(unittest.TestCase):
    def test_package_resolved(self):
        text = '''{"pins": [
          {"identity": "bitkit-core", "location": "https://github.com/synonymdev/bitkit-core",
           "state": {"revision": "b53fa54a", "version": "0.5.18"}},
          {"identity": "ldk-node", "location": "https://github.com/synonymdev/ldk-node",
           "state": {"revision": "190a17d9", "version": "0.7.0-rc.66"}}], "version": 2}'''
        self.assertEqual(spm_pin(text, 'ldk-node'), ('190a17d9', '0.7.0-rc.66'))

    def test_cargo_lock_picks_the_version_the_root_uses(self):
        # Two lightning versions are locked; ldk-node itself depends on 0.2.6.
        lock = '''version = 4
[[package]]
name = "lightning"
version = "0.1.12"
source = "registry+https://github.com/rust-lang/crates.io-index"

[[package]]
name = "lightning"
version = "0.2.6"
source = "registry+https://github.com/rust-lang/crates.io-index"

[[package]]
name = "ldk-node"
version = "0.7.0"
dependencies = ["bitcoin", "lightning 0.2.6", "lightning-types"]
'''
        manifest = '[package]\nname = "ldk-node"\nversion = "0.7.0"\n'
        self.assertEqual(cargo_version(lock, manifest, 'lightning'), '0.2.6')

    def test_cargo_lock_single_version(self):
        lock = '[[package]]\nname = "lightning"\nversion = "0.2.6"\nsource = "registry+x"\n\n' \
               '[[package]]\nname = "ldk-node"\nversion = "0.7.0"\ndependencies = ["lightning"]\n'
        self.assertEqual(cargo_version(lock, '[package]\nname = "ldk-node"\n', 'lightning'), '0.2.6')

    def test_bun_lock(self):
        text = '''{
  "lockfileVersion": 1,
  "packages": {
    "react-native-turbo-lnd": ["react-native-turbo-lnd@0.0.22", "", {}, "sha512-x"],
  },
}'''
        self.assertEqual(bun_version(text, 'react-native-turbo-lnd'), '0.0.22')

    def test_properties(self):
        self.assertEqual(properties('# pinned\nrepository=hsjoberg/lnd\nref=ae185f27\n'),
                         {'repository': 'hsjoberg/lnd', 'ref': 'ae185f27'})


    def test_a_tag_read_with_a_regular_expression(self):
        # Green's gdk release is the TAGNAME line of a shell script in the app repository.
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'green/tools'
            script.mkdir(parents=True)
            (script / 'fetch_gdk_binaries.sh').write_text('RELEASES_URL=x\nTAGNAME="release_0.78.0"\n')
            spec = {'repo': 'https://example.test/gdk', 'track': {'from': 'green:tools/fetch_gdk_binaries.sh',
                                                                  'regex': 'TAGNAME="([^"]+)"', 'tag': '{}'}}
            real_dir, real_rev = common.SOURCES_DIR, update.remote_rev
            common.SOURCES_DIR, update.remote_rev = Path(tmp), lambda repo, ref, required=True: 'abc' if ref == 'refs/tags/release_0.78.0' else None
            try:
                self.assertEqual(update.resolve_rule('gdk', spec), ('https://example.test/gdk', 'abc', '0.78.0', 'release_0.78.0'))
            finally:
                common.SOURCES_DIR, update.remote_rev = real_dir, real_rev

    def test_npm_lock_resolves_the_way_npm_does(self):
        # b needs c ^2; the root has c 1 and b's own copy has c 2. Only production dependencies count.
        lock = {'packages': {
            '': {},
            'node_modules/a': {'version': '1.0.0', 'dependencies': {'c': '^1'}},
            'node_modules/b': {'version': '1.0.0', 'dependencies': {'c': '^2'}},
            'node_modules/b/node_modules/c': {'version': '2.0.0'},
            'node_modules/c': {'version': '1.0.0'},
            'node_modules/jest': {'version': '9.0.0', 'dev': True}}}
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / 'app'
            app.mkdir()
            (app / 'package-lock.json').write_text(__import__('json').dumps(lock))
            (app / 'package.json').write_text('{"dependencies": {"a": "1", "b": "1"}, "devDependencies": {"jest": "9"}}')
            real, common.SOURCES_DIR = common.SOURCES_DIR, Path(tmp)
            try:
                direct, closure = npm_lock({'lock': 'app:package-lock.json', 'package': 'app:package.json'})
            finally:
                common.SOURCES_DIR = real
        self.assertEqual(direct, ['a', 'b'])
        self.assertEqual(closure, ['a@1.0.0', 'b@1.0.0', 'c@1.0.0', 'c@2.0.0'])


class Releases(unittest.TestCase):
    def test_follows_the_highest_version_not_the_latest_name(self):
        # Phoenix tags ios-v2.8.4 after ios-v2.8.3 and ios-v2.10.0 would sort first as text.
        ls = ''.join(f'{sha}\trefs/tags/{name}\n' for sha, name in (
            ('a1', 'ios-v2.8.4'), ('a2', 'ios-v2.8.4^{}'), ('b1', 'ios-v2.10.0'), ('c1', 'android-v9.9.9'), ('d1', 'ios-v2.9.0')))
        real = update.subprocess.run
        update.subprocess.run = lambda *a, **k: type('R', (), {'stdout': ls})()
        try:
            self.assertEqual(update.latest_tag('r', r'ios-v(\d+(?:\.\d+)*)'), ('ios-v2.10.0', 'b1'))
            ls2 = ls.replace('ios-v2.10.0', 'ios-v2.8.5')
            update.subprocess.run = lambda *a, **k: type('R', (), {'stdout': ls2})()
            self.assertEqual(update.latest_tag('r', r'ios-v(\d+(?:\.\d+)*)'), ('ios-v2.9.0', 'd1'))
            self.assertEqual(update.latest_tag('r', r'ios-v(2\.8\.\d+)'), ('ios-v2.8.5', 'b1'))
        finally:
            update.subprocess.run = real


class Branches(unittest.TestCase):
    def test_falls_back_to_the_next_branch(self):
        # Winnow follows its Lightning branch, then main once that branch has merged and gone.
        heads = {'refs/heads/main': 'aaa'}
        real, update.remote_rev = update.remote_rev, lambda repo, ref, required=True: heads.get(ref)
        try:
            self.assertEqual(update.first_branch('r', ['refs/heads/lightning', 'refs/heads/main']), 'aaa')
            heads['refs/heads/lightning'] = 'bbb'
            self.assertEqual(update.first_branch('r', ['refs/heads/lightning', 'refs/heads/main']), 'bbb')
            self.assertEqual(update.first_branch('r', 'refs/heads/main'), 'aaa')
            with self.assertRaises(SystemExit):
                update.first_branch('r', ['refs/heads/gone'])
        finally:
            update.remote_rev = real


class Layout(unittest.TestCase):
    def test_a_new_folder_in_a_complete_tree_is_not_skipped(self):
        # Winnow moved its Lightning screens from Sources/WinnowApp into Sources/WinnowLightningApp.
        with tempfile.TemporaryDirectory() as tmp:
            for d in ('WinnowApp', 'WalletCore', 'LightningCore', 'WinnowLightningApp'):
                (Path(tmp) / 'winnow/Sources' / d).mkdir(parents=True)
            spec = {'code': {'app': ['winnow:Sources/WinnowApp'], 'bitcoin': ['winnow:Sources/WalletCore'],
                             'lightning': ['winnow:Sources/LightningCore']}, 'complete': ['winnow:Sources']}
            real, common.SOURCES_DIR = common.SOURCES_DIR, Path(tmp)
            try:
                self.assertEqual(common.unclaimed(spec), ['winnow:Sources/WinnowLightningApp'])
                spec['code']['app'].append('winnow:Sources/WinnowLightningApp')
                self.assertEqual(common.unclaimed(spec), [])
                del spec['complete']
                spec['code']['app'].pop()
                self.assertEqual(common.unclaimed(spec), [])  # only trees listed in `complete` are checked
            finally:
                common.SOURCES_DIR = real


class Skips(unittest.TestCase):
    def test_a_wallet_can_leave_paths_out_of_a_counted_tree(self):
        # Muun's libwallet holds command-line tools and linters that never build into the app.
        with tempfile.TemporaryDirectory() as tmp:
            for rel in ('lib/address.go', 'lib/cmd/tool.go', 'lib/linters/check.go'):
                path = Path(tmp) / 'muun' / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('package x\n')
            real, common.SOURCES_DIR = common.SOURCES_DIR, Path(tmp)
            try:
                kept, _ = common.counted_files(['muun:lib'], skip=['muun:lib/cmd', 'muun:lib/linters'])
                everything, _ = common.counted_files(['muun:lib'])
            finally:
                common.SOURCES_DIR = real
        self.assertEqual([f.name for f in kept], ['address.go'])
        self.assertEqual(len(everything), 3)


class Review(unittest.TestCase):
    def test_find_moved_block(self):
        now = ['import X', '', 'struct A {', '    func pay() {', '    }', '}']
        self.assertEqual(find(['    func pay() {  ', '    }'], now), 4)  # trailing space is not a change
        self.assertIsNone(find(['    func send() {'], now))

    def test_a_common_line_is_placed_by_its_neighbours(self):
        reviewed = ['func a() {', '    guard ok else { return }', '    pay()', '}',
                    'func b() {', '    guard ok else { return }', '    send()', '}']
        now = ['func b() {', '    guard ok else { return }', '    send()', '}', '',
               'func a() {', '    guard ok else { return }', '    pay()', '}']
        self.assertEqual(locate(reviewed, 6, 6, now), 2)  # b's guard, not a's
        self.assertEqual(locate(reviewed, 2, 2, now), 7)
        self.assertIsNone(locate(['}', '}'], 1, 1, ['}', '}', '}']))  # never unique


class Axis(unittest.TestCase):
    def test_ticks_are_round_and_cover_the_biggest_bar(self):
        end, ticks, step = scale(431_736)
        self.assertEqual(step, 100_000)
        self.assertEqual([t for _, t in ticks], ['0', '100k', '200k', '300k', '400k'])
        self.assertGreater(end, 431_736)
        end, ticks, step = scale(9_100_000)
        self.assertEqual(step, 2_000_000)
        self.assertEqual(ticks[-1], (8_000_000, '8M'))


if __name__ == '__main__':
    unittest.main()
