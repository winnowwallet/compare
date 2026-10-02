"""Lines of code per wallet part (non-blank, non-comment, via cloc) and comment-free,
whitespace-free characters, which do not reward long lines."""
import json

from common import CONFIG, DATA, LANGS, STAGE, cloc, left_out, stage, unclaimed, write_json


def measure(refs, skip=()):
    staged, generated = stage(refs, skip)
    rows = json.loads(cloc(['--json', '--by-file', '--include-lang=' + ','.join(LANGS), str(STAGE)]) or '{}')
    languages, files = {}, 0
    for path, row in rows.items():
        if path in ('header', 'SUM'):
            continue
        files += 1
        languages[row['language']] = languages.get(row['language'], 0) + row['code']
    cloc(['--include-lang=' + ','.join(LANGS), '--strip-comments=nc', '--original-dir', str(STAGE)])
    chars = 0
    for f in sorted(STAGE.rglob('*.nc')):
        chars += sum(1 for ch in f.read_text(errors='ignore') if not ch.isspace())
        f.unlink()
    return {'code': sum(languages.values()), 'chars': chars, 'files': files,
            'languages': dict(sorted(languages.items())), 'generated_excluded': sorted(generated)}


def main():
    result = {}
    for wallet, spec in CONFIG['wallets'].items():
        missing = unclaimed(spec)
        if missing:
            raise SystemExit(f'{wallet} has code that no part of sources.json counts: {", ".join(missing)}. '
                             'Add each to its code parts, or leave it out on purpose by removing it from `complete`.')
        result[wallet] = {part: measure(refs, left_out(spec)) for part, refs in spec['code'].items()}
        print(wallet, {p: v['code'] for p, v in result[wallet].items()})
    write_json(DATA / 'loc.json', result)


if __name__ == '__main__':
    main()
