"""Lines of code per wallet part (non-blank, non-comment, via cloc) and comment-free,
whitespace-free characters, which do not reward long lines."""
import json

import lean
from common import CONFIG, DATA, LANGS, PROOF_STAGE, STAGE, cloc, lean_closure, left_out, stage, unclaimed, write_json


def count(root):
    """cloc's code lines by language, the comment-free characters and the files, of a staged tree."""
    if not root.exists():
        return {}, 0, 0
    rows = json.loads(cloc(['--json', '--by-file', '--include-lang=' + ','.join(LANGS), str(root)]) or '{}')
    languages, files = {}, 0
    for path, row in rows.items():
        if path in ('header', 'SUM'):
            continue
        files += 1
        languages[row['language']] = languages.get(row['language'], 0) + row['code']
    cloc(['--include-lang=' + ','.join(LANGS), '--strip-comments=nc', '--original-dir', str(root)])
    chars = 0
    for f in sorted(root.rglob('*.nc')):
        chars += sum(1 for ch in f.read_text(errors='ignore') if not ch.isspace())
        f.unlink()
    return languages, chars, files


def measure(refs, skip=(), closure=None):
    staged, generated, proof_files, not_built = stage(refs, skip, closure)
    languages, chars, files = count(STAGE)
    result = {'code': sum(languages.values()), 'chars': chars, 'files': files,
              'languages': dict(sorted(languages.items())), 'generated_excluded': sorted(generated)}
    if not_built:
        result['not_built'] = sorted(not_built)
    # Lean proofs (theorem, lemma, example), and the modules the app never imports that hold proofs or the
    # specification they prove against: erased or never compiled into the app, so counted on their own
    if any(f.suffix == '.lean' for f in staged) or proof_files:
        theorems = sum(lean.analyze(f.read_text(errors='ignore'))[1][0] for f in proof_files)
        proof_languages, _, proof_file_count = count(PROOF_STAGE)
        folders = {}
        for f in proof_files:
            folder = '/'.join(f.relative_to(PROOF_STAGE).parts[1:-1][:3]) or '.'
            folders[folder] = folders.get(folder, 0) + lean.analyze(f.read_text(errors='ignore'))[1][0]
        result['proofs'] = {'theorems': theorems, 'lines': sum(proof_languages.values()), 'files': proof_file_count,
                            'theorems_by_folder': dict(sorted((k, v) for k, v in folders.items() if v))}
    return result


def main():
    result = {}
    for wallet, spec in CONFIG['wallets'].items():
        missing = unclaimed(spec)
        if missing:
            raise SystemExit(f'{wallet} has code that no part of sources.json counts: {", ".join(missing)}. '
                             'Add each to its code parts, or leave it out on purpose by removing it from `complete`.')
        closure = lean_closure(spec)
        result[wallet] = {part: measure(refs, left_out(spec), closure if part != 'engine' else None)
                          for part, refs in spec['code'].items()}
        print(wallet, {p: v['code'] for p, v in result[wallet].items()})
    write_json(DATA / 'loc.json', result)


if __name__ == '__main__':
    main()
