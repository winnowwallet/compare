"""Cyclomatic complexity per function from tree-sitter syntax trees, one rule for every language,
over exactly the files loc.py counts.

CC = 1 + each if/guard, for/while/repeat, non-default case/when/match arm, catch, ternary,
&&, || and ??/?: (elvis). Closures, lambdas and nested functions count toward the named function,
method, initializer or computed property that contains them.

Without coverage, CRAP = CC^2 (1 - cov)^3 + CC is bounded below by CC: a function with CC > 12 scores
above 12 whatever its tests, and one with CC > 30 exceeds crap4j's default threshold whatever its tests."""
import statistics
from multiprocessing import Pool
from pathlib import Path

from tree_sitter_language_pack import get_parser

from common import CONFIG, COUNTED, DATA, STAGE, left_out, stage, write_json

LANG = {'.swift': 'swift', '.kt': 'kotlin', '.kts': 'kotlin', '.ts': 'typescript', '.tsx': 'tsx',
        '.js': 'javascript', '.jsx': 'javascript', '.go': 'go', '.rs': 'rust', '.m': 'objc', '.mm': 'objc',
        '.h': 'objc', '.c': 'c', '.cc': 'cpp', '.cpp': 'cpp', '.hpp': 'cpp'}
JS = {'typescript', 'tsx', 'javascript'}
C_LIKE = {'objc', 'c', 'cpp'}
UNITS = {
    'swift': {'function_declaration', 'init_declaration', 'deinit_declaration', 'subscript_declaration',
              'computed_property', 'lambda_literal'},
    'kotlin': {'function_declaration', 'secondary_constructor', 'anonymous_initializer', 'getter', 'setter',
               'lambda_literal'},
    'js': {'function_declaration', 'generator_function_declaration', 'method_definition', 'arrow_function',
           'function_expression', 'function', 'generator_function'},
    'go': {'function_declaration', 'method_declaration', 'func_literal'},
    'rust': {'function_item', 'closure_expression'},
    'c': {'function_definition', 'method_definition', 'block_literal', 'lambda_expression'},
}
BRANCHES = {
    'swift': {'if_statement', 'guard_statement', 'for_statement', 'while_statement', 'repeat_while_statement',
              'catch_block', 'ternary_expression', 'conjunction_expression', 'disjunction_expression',
              'nil_coalescing_expression'},
    'kotlin': {'if_expression', 'for_statement', 'while_statement', 'do_while_statement', 'catch_block',
               'conjunction_expression', 'disjunction_expression', 'elvis_expression'},
    'js': {'if_statement', 'for_statement', 'for_in_statement', 'while_statement', 'do_statement',
           'switch_case', 'catch_clause', 'ternary_expression'},
    'go': {'if_statement', 'for_statement', 'expression_case', 'type_case', 'communication_case'},
    'rust': {'if_expression', 'while_expression', 'for_expression'},
    'c': {'if_statement', 'for_statement', 'for_in_statement', 'while_statement', 'do_statement', 'case_statement',
          'catch_clause', 'conditional_expression'},
}
LOGICAL = {'&&', '||', '??'}


def family(lang):
    return 'js' if lang in JS else 'c' if lang in C_LIKE else lang


def is_branch(node, fam):
    t = node.type
    if t in BRANCHES[fam]:
        if fam == 'c' and t == 'case_statement':
            return node.child_count > 0 and node.children[0].type == 'case'  # not `default:`
        return True
    if fam == 'swift' and t == 'switch_entry':
        return not any(c.type in ('default_keyword', 'default') for c in node.children)
    if fam == 'kotlin' and t == 'when_entry':
        return any(c.type == 'when_condition' for c in node.children)  # not `else ->`
    if fam == 'rust' and t == 'match_arm':
        pattern = node.child_by_field_name('pattern')
        return pattern is None or pattern.text.strip() != b'_'  # the wildcard arm is the default
    if t == 'binary_expression' and fam in ('js', 'go', 'rust', 'c'):
        op = node.child_by_field_name('operator')
        return op is not None and op.type in LOGICAL
    return False


def name_of(node):
    for field in ('name', 'declarator'):
        child = node.child_by_field_name(field)
        if child is not None:
            return child.text.decode(errors='ignore').split('(')[0][:60]
    for c in node.children:
        if c.type in ('simple_identifier', 'identifier', 'field_identifier', 'property_identifier', 'type_identifier'):
            return c.text.decode(errors='ignore')[:60]
    return '(' + node.type + ')'


def analyze(path):
    lang = LANG[Path(path).suffix]
    fam = family(lang)
    tree = get_parser(lang).parse(Path(path).read_bytes())
    units, stack = [], [(tree.root_node, None)]
    # Iterative walk: `owner` is the index of the outermost unit enclosing this node, if any.
    while stack:
        node, owner = stack.pop()
        if owner is None and node.type in UNITS[fam]:
            units.append([1, node.start_point[0] + 1, node.end_point[0] + 1, name_of(node)])
            owner = len(units) - 1
        elif owner is not None and is_branch(node, fam):
            units[owner][0] += 1
        stack.extend((c, owner) for c in reversed(node.children))
    return [(cc, end - start + 1, name, start) for cc, start, end, name in units], tree.root_node.has_error


def summarize(fns):
    cc = sorted(f[0] for f in fns)
    n = len(cc)
    return {
        'functions': n,
        'mean_cc': round(statistics.mean(cc), 2) if n else 0,
        'p90_cc': cc[int(0.9 * (n - 1))] if n else 0,
        'max_cc': cc[-1] if n else 0,
        'cc_le_2': sum(c <= 2 for c in cc),
        'cc_3_12': sum(3 <= c <= 12 for c in cc),
        'cc_gt_12': sum(c > 12 for c in cc),
        'cc_gt_30': sum(c > 30 for c in cc),
    }


def main():
    out = {}
    with Pool() as pool:
        for wallet, spec in CONFIG['wallets'].items():
            out[wallet], every = {}, []
            for part, refs in spec['code'].items():
                if part not in COUNTED:
                    continue
                staged, _ = stage(refs, left_out(spec))
                files = sorted(str(f) for f in staged if f.suffix in LANG)
                fns, errors = [], 0
                for path, (found, has_error) in zip(files, pool.map(analyze, files, chunksize=8)):
                    rel = path.replace(str(STAGE) + '/', '')
                    errors += has_error
                    fns += [(c, n, name, f'{rel}:{line}') for c, n, name, line in found]
                most = sorted(fns, key=lambda f: (-f[0], f[3]))[:5]
                out[wallet][part] = summarize(fns) | {
                    'files': len(files), 'files_with_parse_errors': errors,
                    'most_complex': [{'cc': c, 'function': name, 'at': at} for c, _, name, at in most]}
                every += fns
            out[wallet]['all'] = summarize(every)
            print(wallet, out[wallet]['all']['functions'], 'functions,', out[wallet]['all']['cc_gt_12'], 'above 12')
    write_json(DATA / 'complexity.json', out)


if __name__ == '__main__':
    main()
