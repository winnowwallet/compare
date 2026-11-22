"""Hand-counted cases that pin the measurement rules. Each expected CC is written out as the
branches it counts, so a reader can check the rule, not just the number."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'tools'))

from common import strip_rust_tests  # noqa: E402
from complexity import analyze  # noqa: E402
import lean  # noqa: E402


def scores(name):
    found, has_error = analyze(str(HERE / 'complexity' / name))
    assert not has_error, f'{name} did not parse cleanly'
    return [(cc, fn) for cc, _, fn, _ in found]


class Complexity(unittest.TestCase):
    def test_swift(self):
        self.assertEqual(scores('sample.swift'), [
            (1, 'init'),
            (2, '(computed_property)'),  # ??
            (1, 'Int'),                  # subscript
            # guard, closure ternary, for, if, &&, ||, while, repeat, 2 non-default cases, 2 catches, ??
            (1 + 13, 'f'),
        ])

    def test_kotlin(self):
        self.assertEqual(scores('sample.kt'), [
            (2, '(secondary_constructor)'), (2, '(anonymous_initializer)'), (2, '(getter)'),
            # lambda if, for, if, &&, ||, while, do-while, catch, 2 non-else when arms, elvis
            (1 + 11, 'f'),
        ])

    def test_typescript(self):
        self.assertEqual(scores('sample.ts'), [
            (1 + 2, '(arrow_function)'),  # nested arrow's ternary folds in, ??
            # for-of, if, &&, ||, while, do, case 1, catch; a regex with a quote in it does not derail the parse
            (1 + 8, 'm'),
            (2, '(arrow_function)'),      # class field arrow: if
            (1, 'f'),
        ])

    def test_go(self):
        self.assertEqual(scores('sample.go'), [
            # func literal if, for, if, &&, ||, case 1,2, type case, select case (defaults excluded)
            (1 + 8, 'f'),
            (1, 'm'),
        ])

    def test_rust(self):
        self.assertEqual(scores('sample.rs'), [
            # closure if, for, if, &&, ||, while, 2 non-wildcard match arms; `?`, `loop` and `_` add nothing
            (1 + 8, 'm'),
            (1, 'f'),
            (2, 'd'),
        ])

    def test_lean(self):
        found, proofs = lean.analyze((HERE / 'complexity' / 'sample.lean').read_text())
        self.assertEqual([(cc, fn) for cc, _, fn, _ in found], [
            # if, &&, ||, else if, for, unless, while, catch, 2 non-wildcard match arms (or-pattern is one),
            # 1 non-wildcard fun alternative, the where helper's if; strings, a char and comments add nothing
            (1 + 12, 'f'),
            (1 + 2, 'g'),                          # two non-wildcard arms of a definition by patterns
            (1 + 3, 'h'),                          # three arms with a string or char pattern, and `_, _`
            (2, '(instance ToString Bool)'),       # if
        ])
        self.assertEqual(proofs, (1, 2))           # the theorem is a proof, not a function


class RustTests(unittest.TestCase):
    def test_inline_test_modules_are_removed(self):
        source = '''fn a() { let s = "}"; let c = '}'; let r = r#"}"#; }
#[cfg(test)]
mod tests {
    #[test] fn x() { let s = "{"; /* } */ }
}
fn b<'a>(x: &'a str) {}
#[cfg(all(test, feature = "std"))]
pub(crate) mod more { fn y() {} }
fn c() {}
'''
        self.assertEqual(strip_rust_tests(source).split(), '''fn a() { let s = "}"; let c = '}'; let r = r#"}"#; }
fn b<'a>(x: &'a str) {}
fn c() {}'''.split())


if __name__ == '__main__':
    unittest.main()


class LeanProofs(unittest.TestCase):
    TEXT = '\n'.join([
        'import Std.Data.HashMap',          # 1
        'public import Winnow.Keys',        # 2
        '',                                 # 3
        '/-- A doc comment. -/',            # 4
        'def double (n : Nat) : Nat := 2 * n',  # 5
        '',                                 # 6
        '@[simp] private theorem double_add (a b : Nat) :',  # 7
        '    double (a + b) = double a + double b := by',     # 8
        '  simp [double]; omega',           # 9
        '',                                 # 10
        'example : double 2 = 4 := rfl',    # 11
        'def triple (n : Nat) : Nat := 3 * n',  # 12
    ])

    def test_proofs_are_split_out_keeping_line_numbers(self):
        code, proofs = lean.split_proofs(self.TEXT)
        code, proofs = code.split('\n'), proofs.split('\n')
        self.assertEqual(len(code), 12)
        self.assertEqual(len(proofs), 12)
        # the theorem (lines 7-9) and the example (11) leave the code; the defs stay where they were
        self.assertEqual([k + 1 for k, line in enumerate(proofs) if line.strip()], [7, 8, 9, 11])
        self.assertEqual(code[4], 'def double (n : Nat) : Nat := 2 * n')
        self.assertEqual(code[11], 'def triple (n : Nat) : Nat := 3 * n')
        self.assertFalse(any('theorem' in line or 'example' in line for line in code))
        # and the proof count agrees with what is split out
        self.assertEqual(lean.analyze(self.TEXT)[1], (2, 4))

    def test_imports(self):
        self.assertEqual(lean.imports(self.TEXT), ['Std.Data.HashMap', 'Winnow.Keys'])
        self.assertEqual(lean.imports('-- import Not.This\n/- import Nor.This -/\nimport This.One\n'), ['This.One'])


class TestFiles(unittest.TestCase):
    def test_recognised(self):
        import tests as t
        yes = ['tests/unit/wallet.test.ts', 'src/__tests__/a.tsx', 'BitkitTests/PaykitTests.swift',
               'gaiosUITests/Screens/Home.swift', 'libwallet/address_test.go', 'phoenix-shared/src/commonTest/kotlin/A.kt',
               'Lean/MultisigTest.lean', 'LeanApp/RecordsTest.lean', 'src/fuzz/target.rs', 'crate/src/tests.rs']
        no = ['src/wallet.ts', 'Bitkit/Testimony.swift', 'libwallet/testament.go', 'Lean/Winnow/Wallet/Spend.lean',
              'android/app/src/test/java/A.kt', 'phoenix-android/src/androidTest/A.kt', 'desktop/tests/a.ts',
              'shared/src/androidMain/kotlin/A.kt']
        for path in yes:
            self.assertTrue(t.is_test(tuple(path.split('/'))), path)
        for path in no:
            self.assertFalse(t.is_test(tuple(path.split('/'))), path)
