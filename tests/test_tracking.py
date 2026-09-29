"""The rules that move pins and judge how fresh the hand review is. Each case is the shape of a
real file the rule reads: Bitkit's Package.resolved, LDK Node's Cargo.lock, Blixt's bun.lock and
react-native-turbo-lnd's lnd-source.properties."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))

from evidence import find  # noqa: E402
from render import scale  # noqa: E402
import update  # noqa: E402
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


class Review(unittest.TestCase):
    def test_find_moved_block(self):
        now = ['import X', '', 'struct A {', '    func pay() {', '    }', '}']
        self.assertEqual(find(['    func pay() {  ', '    }'], now), 4)  # trailing space is not a change
        self.assertIsNone(find(['    func send() {'], now))


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
