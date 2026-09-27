"""Hand-counted cases that pin the measurement rules. Each expected CC is written out as the
branches it counts, so a reader can check the rule, not just the number."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'tools'))

from common import strip_rust_tests  # noqa: E402
from complexity import analyze  # noqa: E402


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
