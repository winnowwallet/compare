"""Every hand-reviewed fact cites code. Check each citation names a file that exists at the
revision it was reviewed against (reviewed.json) and lines inside it; fail the build otherwise.

Then compare each cited line range with the same file at today's pinned revision and write
data/drift.json: which citations still point at the same code, which moved within their file,
and which changed or disappeared since the review. The page reports it, so readers can see how
fresh the hand review is.

  evidence.py           check, and write data/drift.json
  evidence.py --adopt [source ...]
                        start a re-review: move reviewed.json to today's pins (for the named
                        sources, or all), follow citations whose code only moved, and list the
                        ones to check by hand
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone

from common import CONFIG, DATA, REVIEWED, ROOT, source_dir, write_config, write_json

VALUES = {'yes', 'partial', 'engine-only', 'no', 'unknown'}
CITATION = re.compile(r'([a-z0-9-]+):([^:]+?)(?::(\d+)(?:-(\d+))?)?')
PROFILES = ROOT / 'wallets.json'


def citations(text):
    for item in (t.strip() for t in text.split(';') if t.strip()):
        m = CITATION.fullmatch(item)
        if not m:
            raise ValueError(f'unreadable citation {item!r}')
        yield m.groups()


def facts():
    """(wallet, fact name, citation text, file, json path to the text) for every cited fact."""
    for wallet in CONFIG['wallets']:
        path = ROOT / f'features/{wallet.lower()}.json'
        for key, cell in json.loads(path.read_text())['features'].items():
            yield wallet, f'features.{key}', cell['evidence'], path, ('features', key, 'evidence')
    for wallet, profile in json.loads(PROFILES.read_text())['profiles'].items():
        for key, value in profile.items():
            if isinstance(value, dict) and value.get('cite'):
                yield wallet, f'profile.{key}', value['cite'], PROFILES, ('profiles', wallet, key, 'cite')


def blob(source, rev, path):
    r = subprocess.run(['git', 'cat-file', 'blob', f'{rev}:{path}'], cwd=source_dir(source), capture_output=True)
    return r.stdout.decode(errors='ignore').splitlines() if r.returncode == 0 else None


def find(block, lines):
    """First line number where `block` appears in `lines`, comparing without trailing space."""
    want = [l.rstrip() for l in block]
    have = [l.rstrip() for l in lines]
    for i in range(len(have) - len(want) + 1):
        if have[i:i + len(want)] == want:
            return i + 1
    return None


def drift(source, path, a, b, reviewed_lines):
    """same | moved (with the new first line) | changed | gone, from the review to today's pin."""
    now = blob(source, CONFIG['sources'][source]['rev'], path)
    if now is None:
        return 'gone', None
    if not a:
        return ('same' if now == reviewed_lines else 'changed'), None
    first, last = int(a), int(b or a)
    block = reviewed_lines[first - 1:last]
    if now[first - 1:last] == block:
        return 'same', None
    at = find(block, now)
    return ('moved', at) if at else ('changed', None)


def check():
    problems, items = [], []
    for wallet, fact, text, _, _ in facts():
        if fact.startswith('features.') and fact != 'features.license':
            cell = json.loads((ROOT / f'features/{wallet.lower()}.json').read_text())['features'][fact[9:]]
            if cell['value'] not in VALUES:
                problems.append(f'{wallet}.{fact}: value {cell["value"]!r}')
        for source, path, a, b in citations(text):
            cite = f'{source}:{path}' + (f':{a}' if a else '') + (f'-{b}' if b else '')
            if source not in REVIEWED['sources']:
                problems.append(f'{wallet} {fact}: {source} is not in reviewed.json')
                continue
            lines = blob(source, REVIEWED['sources'][source]['rev'], path)
            if lines is None:
                problems.append(f'{wallet} {fact}: {cite} does not exist at the reviewed revision')
                continue
            if any(n and int(n) > len(lines) for n in (a, b)):
                problems.append(f'{wallet} {fact}: {source}:{path} has {len(lines)} lines, cites {b or a}')
                continue
            status, at = drift(source, path, a, b, lines)
            items.append({'wallet': wallet, 'fact': fact, 'cite': cite, 'status': status, **({'now_at': at} if at else {})})
    return problems, items


def summary(items):
    count = lambda rows: {s: sum(r['status'] == s for r in rows) for s in ('same', 'moved', 'changed', 'gone')}
    dates = sorted(r['date'] for r in REVIEWED['sources'].values())
    return {
        'reviewed': dates[0], 'reviewed_latest': dates[-1], 'measured': CONFIG['snapshot'], 'citations': len(items), **count(items),
        'by_wallet': {w: count([r for r in items if r['wallet'] == w]) for w in CONFIG['wallets']},
        'changed_or_gone': [r for r in items if r['status'] in ('changed', 'gone')],
        'moved_within_file': [r for r in items if r['status'] == 'moved'],
    }


def adopt(items, sources):
    """Move the review to today's pins. Citations whose code only moved follow it; the rest are listed.
    Citation strings are replaced in place, so the files keep their layout."""
    unknown = set(sources) - set(REVIEWED['sources'])
    if unknown:
        sys.exit(f'not in reviewed.json: {" ".join(sorted(unknown))}')
    items = [r for r in items if r['cite'].split(':')[0] in sources]
    moved = {(r['wallet'], r['fact'], r['cite']): r['now_at'] for r in items if r['status'] == 'moved'}
    texts = {}
    for wallet, fact, text, path, _ in facts():
        new = []
        for item in (t.strip() for t in text.split(';') if t.strip()):
            source, file, a, b = CITATION.fullmatch(item).groups()
            at = moved.get((wallet, fact, item))
            if at:
                item = f'{source}:{file}:{at}' + (f'-{at + int(b) - int(a)}' if b else '')
            new.append(item)
        if '; '.join(new) != text:
            texts.setdefault(path, {})[json.dumps(text, ensure_ascii=False)] = json.dumps('; '.join(new), ensure_ascii=False)
    for path, swaps in texts.items():
        content = path.read_text()
        for old, new in swaps.items():
            content = content.replace(old, new)
        path.write_text(content)
    today = datetime.now(timezone.utc).date().isoformat()
    for source in sources:
        REVIEWED['sources'][source] = {**{k: CONFIG['sources'][source][k] for k in ('repo', 'rev')}, 'date': today}
    write_config(ROOT / 'reviewed.json', REVIEWED)
    todo = [r for r in items if r['status'] in ('changed', 'gone')]
    print(f'reviewed.json now names today\'s pins; {len(moved)} citations followed their code.')
    print(f'Check these {len(todo)} by hand, then ./build evidence:' if todo else 'Nothing else to check.')
    for r in todo:
        print(f'  {r["status"]:8} {r["wallet"]} {r["fact"]}: {r["cite"]}')


def main():
    problems, items = check()
    if problems:
        sys.exit('\n'.join(problems))
    if '--adopt' in sys.argv:
        return adopt(items, sys.argv[sys.argv.index('--adopt') + 1:] or list(REVIEWED['sources']))
    s = summary(items)
    write_json(DATA / 'drift.json', s)
    print(f'{s["citations"]} citations resolve at the reviewed revisions; since the review '
          f'{s["same"]} are unchanged, {s["moved"]} moved, {s["changed"]} changed, {s["gone"]} gone')


if __name__ == '__main__':
    main()
