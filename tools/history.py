"""Keep one row per snapshot in data/history.json: the exact revisions measured and each wallet's
headline numbers. The row for the current snapshot is rewritten from data/ on every build, so it
always matches the measurement; earlier rows are left as they were measured. Any row can be
rebuilt from the commit that recorded it."""
import json

from common import CONFIG, DATA, dumps

PATH = DATA / 'history.json'


def row():
    loc = json.loads((DATA / 'loc.json').read_text())
    cc = json.loads((DATA / 'complexity.json').read_text())
    deps = json.loads((DATA / 'deps.json').read_text())
    vend = json.loads((DATA / 'vendored.json').read_text())
    wallets = {}
    for w in CONFIG['wallets']:
        a = cc[w]['all']
        wallets[w] = {
            'lines': sum(p['code'] for p in loc[w].values()),
            **{f'lines_{part}': p['code'] for part, p in loc[w].items()},
            'characters': sum(p['chars'] for p in loc[w].values()),
            'functions': a['functions'], 'cc_gt_12': a['cc_gt_12'], 'cc_gt_30': a['cc_gt_30'], 'max_cc': a['max_cc'],
            'packages': deps[w]['total'], 'vendored_lines': vend[w]['copied_lines'],
        }
    return {'date': CONFIG['snapshot'], 'method': CONFIG['method'],
            'sources': {k: s['rev'] for k, s in CONFIG['sources'].items()}, 'wallets': wallets}


def main():
    rows = json.loads(PATH.read_text())['snapshots'] if PATH.exists() else []
    new = row()
    rows = sorted([r for r in rows if r['date'] != new['date']] + [new], key=lambda r: r['date'])
    PATH.write_text(dumps({
        'about': 'One row per snapshot: the revisions measured and each wallet\'s headline numbers. '
                 'Rows with a different method were counted under earlier rules.',
        'snapshots': rows}) + '\n')
    print(f'{len(rows)} snapshots, {rows[0]["date"]} to {rows[-1]["date"]}')


if __name__ == '__main__':
    main()
