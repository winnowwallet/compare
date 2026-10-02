"""Render site/index.html and site/data.json from data/, features/ and wallets.json.
No number on the page is typed by hand. Citations link to the revision they were reviewed
against; everything measured links to today's pins. Sentences whose wording depends on the
numbers are checked in claims(), so a daily run fails rather than publish one that stopped
being true."""
import html
import json
import math
import re
from datetime import date

from common import CONFIG, COUNTED, DATA, REVIEWED, ROOT, write_json
from evidence import blob

esc = html.escape
PROFILES = json.loads((ROOT / 'wallets.json').read_text())
ORDER = PROFILES['order']
loc = json.loads((DATA / 'loc.json').read_text())
cc = json.loads((DATA / 'complexity.json').read_text())
deps = json.loads((DATA / 'deps.json').read_text())
vend = json.loads((DATA / 'vendored.json').read_text())
drift = json.loads((DATA / 'drift.json').read_text())
history_all = json.loads((DATA / 'history.json').read_text())['snapshots']
history = [r for r in history_all if r['method'] == CONFIG['method']]  # earlier rules counted different things
features = {w: json.loads((ROOT / f'features/{w.lower()}.json').read_text())['features'] for w in ORDER}
ROWS = json.loads((ROOT / 'features/rows.json').read_text())
P = PROFILES['profiles']
SNAPSHOT = date.fromisoformat(CONFIG['snapshot'])


def day(d):
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f'{d.day} {d:%B %Y}'


SNAPSHOT_TEXT = day(SNAPSHOT)


def link(source, path, line=None, end=None, text=None, reviewed=False):
    spec = (REVIEWED if reviewed else CONFIG)['sources'][source]
    base = spec['repo'].removesuffix('.git')
    anchor = f'#L{line}' + (f'-L{end}' if end else '') if line else ''
    shown = text or (path.rsplit('/', 1)[-1] + (f':{line}' if line else ''))
    breakable = esc(shown).replace('.', '.<wbr>').replace(':', '<wbr>:')  # wrap at names, not mid-word
    return f'<a href="{esc(base + "/blob/" + spec["rev"] + "/" + path.replace(" ", "%20") + anchor)}"><code>{breakable}</code></a>'


def cite_links(text):
    out = []
    for item in (t.strip() for t in text.split(';') if t.strip()):
        source, path, a, b = re.fullmatch(r'([a-z0-9-]+):([^:]+?)(?::(\d+)(?:-(\d+))?)?', item).groups()
        out.append(link(source, path, a, b, reviewed=True))
    return ' '.join(out)


def name_cell(w, tag='th'):
    inner = f'<strong>{w}</strong>' if w == 'Winnow' else w
    return f'<th scope="row">{inner}</th>' if tag == 'th' else inner


def versions(text):
    """{version:lnd-zeus} in a hand-written fact is the version measured today."""
    return re.sub(r'\{version:([a-z0-9-]+)\}', lambda m: CONFIG['sources'][m.group(1)]['version'], text)


def fact(value):
    if isinstance(value, dict):
        cite = f' <span class="cite">{cite_links(value["cite"])}</span>' if value.get('cite') else ''
        return esc(versions(value['text'])) + cite
    return esc(versions(value))


# ── at a glance ────────────────────────────────────────────────
glance = '\n'.join(
    f'<tr>{name_cell(w)}<td>{fact(P[w]["built_with"])}</td><td>{fact(P[w]["engine"])}</td><td>{fact(P[w]["chain_data"])}</td>'
    f'<td>{fact(P[w]["third_party"])}</td><td>{fact(P[w]["distribution"])}</td></tr>' for w in ORDER)

# ── code size chart and table ──────────────────────────────────
ROLES = [('app', 'App', 'app'), ('bitcoin', 'Own Bitcoin library', 'btc')]


def tot(w, key):
    """The wallet's own code: its app, and the Bitcoin library in its repository if it has one."""
    return sum(p[key] for part, p in loc[w].items() if part in COUNTED)


def k(n):
    return f'{n / 1000:.0f}k' if n < 1_000_000 else f'{n / 1_000_000:.1f}M'


def tick_label(n):
    return '0' if not n else f'{n / 1000:g}k' if n < 1_000_000 else f'{n / 1_000_000:g}M'


def scale(biggest):
    """A round tick step giving at most five intervals, and an axis end just past the biggest bar."""
    exp = 10 ** math.floor(math.log10(biggest / 4))
    step = next(m * exp for m in (1, 2, 2.5, 5, 10) if m * exp * 5 >= biggest)
    end = biggest * 1.06
    return end, [(v, tick_label(v)) for v in range(0, int(end), int(step))], step


MAX, TICKS, GRID = {}, {}, {}
for u, key in (('l', 'code'), ('c', 'chars')):
    MAX[u], TICKS[u], step = scale(max(tot(w, key) for w in ORDER))
    GRID[u] = f'{100 * step / MAX[u]:.4f}%'


def pct(n, u):
    return f'{100 * n / MAX[u]:.3f}%'


W_L, W_C = tot('Winnow', 'code'), tot('Winnow', 'chars')
rows, size_table = [], []
for w in ORDER:
    segs, tip_l, tip_c = [], [], []
    for role, label, cls in ROLES:
        if role in loc[w]:
            p = loc[w][role]
            segs.append(f'<span class="seg {cls}" style="--l:{pct(p["code"], "l")};--c:{pct(p["chars"], "c")}"></span>')
            tip_l.append(f'{label} {p["code"]:,}')
            tip_c.append(f'{label} {p["chars"] / 1e6:.2f}M')
    L, C = tot(w, 'code'), tot(w, 'chars')
    rows.append(
        f'<div class="bar-row" tabindex="0" aria-label="{w}: {L:,} lines, {C / 1e6:.1f} million characters">'
        f'<span class="name">{name_cell(w, "span")}</span><span class="track"><span class="bar">{"".join(segs)}</span></span>'
        f'<span class="total"><span class="u-l">{k(L)}</span><span class="u-c">{k(C)}</span></span>'
        f'<span class="tip" aria-hidden="true"><b>{w}</b> <span class="u-l">{L:,} lines · {" · ".join(tip_l)}</span>'
        f'<span class="u-c">{C / 1e6:.2f}M characters · {" · ".join(tip_c)}</span></span></div>')
    cells = []
    for role, _, _ in ROLES:
        if role in loc[w]:
            cells.append(f'<td class="{"lib" if role == "bitcoin" else "num"}">{loc[w][role]["code"]:,}</td>')
        else:
            cells.append('<td class="lib dim">—</td>')
    if 'engine' in loc[w]:
        names = ', '.join(dict.fromkeys(CONFIG['sources'][r.split(':')[0]]['label'] for r in CONFIG['wallets'][w]['code']['engine']))
        engine_cell = f'<td class="lib">{loc[w]["engine"]["code"]:,} <span class="dim">{esc(names)}</span></td>'
    else:
        engine_cell = '<td class="lib dim">None embedded</td>'
    rel = '—' if w == 'Winnow' else f'{L / W_L:.1f}× · {C / W_C:.1f}×'
    size_table.append(f'<tr>{name_cell(w)}{"".join(cells)}<td class="num"><strong>{L:,}</strong></td>'
                      f'<td class="num">{C / 1e6:.2f}M</td><td class="num">{rel}</td>{engine_cell}</tr>')
axis = [''.join(f'<span class="u-{u}" style="left:{100 * v / MAX[u]:.3f}%">{t}</span>' for v, t in TICKS[u]) for u in 'lc']

# ── languages ──────────────────────────────────────────────────
LANG_GROUP = {'Swift': 'Swift', 'Kotlin': 'Kotlin', 'Rust': 'Rust', 'Go': 'Go', 'TypeScript': 'TypeScript/JS',
              'JavaScript': 'TypeScript/JS', 'JSX': 'TypeScript/JS', 'Objective-C': 'C family',
              'Objective-C++': 'C family', 'C': 'C family', 'C++': 'C family', 'C/C++ Header': 'C family'}
LANGS = ['Swift', 'Kotlin', 'Rust', 'Go', 'TypeScript/JS', 'C family']
languages, lang_rows = {}, []
for w in ORDER:
    shares = {}
    for part in loc[w].values():
        for lang, n in part['languages'].items():
            shares[LANG_GROUP[lang]] = shares.get(LANG_GROUP[lang], 0) + n
    total = sum(shares.values())
    languages[w] = {l: round(100 * shares.get(l, 0) / total, 2) for l in LANGS}
    cells = ''.join(f'<td class="num">{languages[w][l]:.0f}%</td>' if languages[w][l] >= 0.5 else
                    ('<td class="num">&lt;1%</td>' if languages[w][l] > 0 else '<td class="num dim">—</td>') for l in LANGS)
    lang_rows.append(f'<tr>{name_cell(w)}{cells}</tr>')

# ── complexity ─────────────────────────────────────────────────
worst_pct = max(cc[w]['all']['cc_gt_12'] / cc[w]['all']['functions'] for w in ORDER)
cc_rows, cc_parts = [], []
for w in ORDER:
    a = cc[w]['all']
    p12, p30 = 100 * a['cc_gt_12'] / a['functions'], 100 * a['cc_gt_30'] / a['functions']
    bar = f'<span class="minibar" style="--w:{100 * (a["cc_gt_12"] / a["functions"]) / worst_pct:.1f}%" aria-hidden="true"></span>'
    cc_rows.append(f'<tr>{name_cell(w)}<td class="num">{a["functions"]:,}</td><td class="num">{a["mean_cc"]:.1f}</td>'
                   f'<td class="num">{a["p90_cc"]}</td><td class="num">{a["max_cc"]}</td>'
                   f'<td class="num">{a["cc_gt_12"]:,} <span class="dim">({p12:.1f}%)</span></td><td class="bar-cell">{bar}</td>'
                   f'<td class="num">{a["cc_gt_30"]:,} <span class="dim">({p30:.2f}%)</span></td></tr>')
    for role, label, _ in ROLES:
        if role in cc[w]:
            p = cc[w][role]
            top = p['most_complex'][0]
            source, _, rest = top['at'].partition('/')
            path, _, line = rest.rpartition(':')
            cc_parts.append(f'<tr><th scope="row">{w} · {label.lower()}</th><td class="num">{p["functions"]:,}</td>'
                            f'<td class="num">{p["mean_cc"]:.1f}</td><td class="num">{p["p90_cc"]}</td><td class="num">{p["max_cc"]}</td>'
                            f'<td class="num">{p["cc_gt_12"]:,}</td><td class="num">{p["cc_gt_30"]:,}</td>'
                            f'<td>{link(source, path, line, text=top["function"][:32])}</td></tr>')

# ── dependencies ───────────────────────────────────────────────
def dep_cell(w, key):
    v = deps[w].get(key)
    return f'<td class="num">{len(v):,}</td>' if v else '<td class="num dim">—</td>'


dep_rows = '\n'.join([
    '<tr><th scope="row">Swift packages</th>' + ''.join(dep_cell(w, 'spm') for w in ORDER) + '</tr>',
    '<tr><th scope="row">Kotlin libraries</th>' + ''.join(dep_cell(w, 'kotlin') for w in ORDER) + '</tr>',
    '<tr><th scope="row">Rust crates, inside prebuilt libraries</th>' + ''.join(dep_cell(w, 'rust') for w in ORDER) + '</tr>',
    '<tr><th scope="row">Go modules, inside the Go library</th>' + ''.join(dep_cell(w, 'go') for w in ORDER) + '</tr>',
    '<tr><th scope="row">npm packages</th>' + ''.join(dep_cell(w, 'npm') for w in ORDER) + '</tr>',
    '<tr><th scope="row">CocoaPods from the trunk</th>' + ''.join(dep_cell(w, 'pods') for w in ORDER) + '</tr>',
    '<tr class="sum"><th scope="row">Third-party packages</th>' + ''.join(f'<td class="num"><strong>{deps[w]["total"]:,}</strong></td>' for w in ORDER) + '</tr>',
])


def vendored_text(w):
    v = vend[w]
    if not v['copied_packages']:
        return 'None'
    biggest = sorted(v['copied_packages'].items(), key=lambda kv: -kv[1]['lines'])
    shown = ', '.join(re.sub(r'^.*/', '', p).removesuffix('.ts') for p, _ in biggest[:6])
    more = f' and {len(biggest) - 6} more' if len(biggest) > 6 else ''
    folder = sorted({p.rsplit('/', 1)[0] for p in v['copied_packages']})
    return f'{v["copied_lines"]:,} lines in {", ".join(f"<code>{esc(f)}</code>" for f in folder)}: {esc(shown)}{esc(more)}'


dep_text = '\n'.join(f'<tr>{name_cell(w)}<td>{fact(P[w]["libraries"])}</td>'
                     f'<td>{esc(P[w]["bitcoin_library_not_counted"]) if P[w]["bitcoin_library_not_counted"] else "—"}</td>'
                     f'<td>{fact(P[w]["prebuilt"])}</td><td>{vendored_text(w)}</td><td>{esc(P[w]["patched"])}</td></tr>' for w in ORDER)

# ── features ───────────────────────────────────────────────────
GROUPS = [(g['title'], [(r['key'], r['label']) for r in g['rows']]) for g in ROWS['groups']]
MARK = {'yes': ('f-yes', '✓', 'Yes'), 'partial': ('f-partial', '◐', 'Partial'), 'engine-only': ('f-engine', '○', 'Engine only'),
        'no': ('f-no', '–', 'No'), 'unknown': ('f-no', '?', 'Unknown')}
feat_rows = []
for title, items in GROUPS:
    feat_rows.append(f'<tr class="group"><th scope="rowgroup" colspan="{len(ORDER) + 1}">{title}</th></tr>')
    for key, label in items:
        cells = []
        for w in ORDER:
            f = features[w][key]
            cls, glyph, word = MARK[f['value']]
            cells.append(f'<td class="{cls}" title="{esc(f["note"])}"><span aria-hidden="true">{glyph}</span> {word}</td>')
        feat_rows.append(f'<tr><th scope="row">{label}</th>{"".join(cells)}</tr>')
feat_rows.append(f'<tr class="group"><th scope="rowgroup" colspan="{len(ORDER) + 1}">License</th></tr><tr><th scope="row">Source license</th>' +
                 ''.join(f'<td>{esc(features[w]["license"]["value"])}</td>' for w in ORDER) + '</tr>')
evidence = []
for w in ORDER:
    items = [f'<li><strong>{label}:</strong> {MARK[features[w][key]["value"]][2]}. {esc(features[w][key]["note"].rstrip("."))}. '
             f'{cite_links(features[w][key]["evidence"])}</li>' for _, group in GROUPS for key, label in group]
    evidence.append(f'<h4>{w}</h4><ul class="evidence">{"".join(items)}</ul>')

# ── sources, other approaches ──────────────────────────────────
used = {w: [r.split(':')[0] for part in CONFIG['wallets'][w]['code'].values() for r in part] for w in ORDER}
source_rows = []
for w in ORDER:
    app_key = CONFIG['wallets'][w]['app_source']
    engines = sorted({k for k in used[w] if k != app_key}, key=list(CONFIG['sources']).index)  # embedded engines
    extra = sorted({c['source'] for c in CONFIG['wallets'][w]['deps'].get('cargo', [])} - set(engines) - {app_key},
                   key=list(CONFIG['sources']).index)

    def src(key):
        s = CONFIG['sources'][key]
        return f'<a href="{esc(s["repo"])}/tree/{s["rev"]}"><code>{esc(s["label"])}</code></a>'
    engine_cell = ', '.join(src(k) for k in engines) or 'In the same repository'
    extra_cell = ', '.join(src(k) for k in extra) or '—'
    source_rows.append(f'<tr>{name_cell(w)}<td>{src(app_key)}</td><td>{engine_cell}</td><td>{extra_cell}</td></tr>')
other = '\n'.join(f'<li><strong>{esc(n)}</strong> {esc(t)}</li>' for n, t in PROFILES['not_compared'])

# ── over time ──────────────────────────────────────────────────
TRENDS = [('lines', 'Lines of code'), ('packages', 'Third-party packages'), ('cc_gt_12', 'Functions above CC 12')]
SPARK_W, SPARK_H, PAD = 144, 32, 6
first_day = date.fromisoformat(history[0]['date'])
earlier = [r for r in history_all if r['method'] != CONFIG['method']]


def spark(w, key, label):
    """A sparkline tile: today's value, the change since tracking began, and every snapshot in between.
    The y range is at least a tenth of the value, so a small change does not fill the tile."""
    rows = [r for r in history if w in r['wallets'] and key in r['wallets'][w]]
    days = [date.fromisoformat(r['date']) for r in rows]
    vals = [r['wallets'][w][key] for r in rows]
    span_days = (days[-1] - days[0]).days
    xs = [PAD + (SPARK_W - 2 * PAD) * ((d - days[0]).days / span_days if span_days else 1) for d in days]
    lo, hi = min(vals), max(vals)
    pad = max(hi - lo, 0.1 * hi, 1) - (hi - lo)
    lo, hi = lo - pad / 2, hi + pad / 2
    ys = [SPARK_H - PAD - (SPARK_H - 2 * PAD) * (v - lo) / (hi - lo) for v in vals]
    pts = ' '.join(f'{x:.1f},{y:.1f}' for x, y in zip(xs, ys))
    now, was = vals[-1], vals[0]
    if len(vals) == 1:
        change = '<span class="delta">first snapshot</span>'
    elif now == was:
        change = '<span class="delta">no change</span>'
    else:
        share = 100 * (now - was) / was if was else None
        pct_text = '' if share is None else ' (<0.1%)' if abs(share) < 0.05 else f' ({share:+.1f}%)'
        change = f'<span class="delta">{esc(f"{now - was:+,}{pct_text}".replace("-", "−"))}</span>'
    aria = (f'{w}, {label.lower()}: {now:,} on {day(days[-1])}' +
            (f', from {was:,} on {day(days[0])}' if len(vals) > 1 else '') + '. Arrow keys step through snapshots.')
    return (f'<td class="trend-cell"><span class="val">{now:,}</span>{change}'
            f'<svg class="spark" viewBox="0 0 {SPARK_W} {SPARK_H}" width="{SPARK_W}" height="{SPARK_H}" tabindex="0" role="img" aria-label="{esc(aria)}" '
            f'data-d="{",".join(r["date"] for r in rows)}" data-v="{",".join(map(str, vals))}" '
            f'data-x="{",".join(f"{x:.1f}" for x in xs)}" data-y="{",".join(f"{y:.1f}" for y in ys)}">'
            f'<line class="cross" x1="0" x2="0" y1="0" y2="{SPARK_H}"/>'
            + (f'<polyline points="{pts}"/>' if len(vals) > 1 else '') +
            f'<circle class="end" cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="4"/><circle class="hover" r="4"/></svg></td>')


trend_rows = '\n'.join(f'<tr>{name_cell(w)}{"".join(spark(w, key, label) for key, label in TRENDS)}</tr>' for w in ORDER)


def moved(prev, row):
    if prev is None:
        return 'First snapshot'
    notes = ['Counting rules changed'] if prev['method'] != row['method'] else []
    keys = [k for k, rev in row['sources'].items() if prev['sources'].get(k) != rev]
    return '; '.join(notes + [', '.join(keys)] if keys else notes) or '—'


RECENT = 90
recent = list(enumerate(history))[-RECENT:][::-1]
snapshot_tables = []
for n, (key, label) in enumerate(TRENDS):
    body = '\n'.join(
        f'<tr><th scope="row">{day(r["date"])}</th>' +
        ''.join(f'<td class="num">{r["wallets"][w][key]:,}</td>' if w in r['wallets'] else '<td class="num dim">—</td>' for w in ORDER) +
        (f'<td class="wrap">{esc(moved(history[i - 1] if i else None, r))}</td>' if n == 0 else '') + '</tr>'
        for i, r in recent)
    extra = '<th scope="col">Sources that moved</th>' if n == 0 else ''
    snapshot_tables.append(
        f'<div class="table-wrap" role="region" tabindex="0" aria-label="Scrollable table"><table class="snapshots">'
        f'<caption>{label}</caption><thead><tr><th scope="col">Snapshot</th>'
        + ''.join(f'<th scope="col" class="num">{w}</th>' for w in ORDER) + f'{extra}</tr></thead><tbody>\n{body}\n</tbody></table></div>')
older = (f'<p>The page lists the latest {RECENT} snapshots; <a href="data.json">data.json</a> has all {len(history)}.</p>'
         if len(history) > RECENT else '')

# ── how fresh the hand review is ───────────────────────────────
reviewed_text = (f"on {day(drift['reviewed'])}" if drift['reviewed'] == drift['reviewed_latest'] else
                 f'between {day(drift["reviewed"])} and {day(drift["reviewed_latest"])}')
stale = drift['changed'] + drift['gone']
if not stale and not drift['moved']:
    drift_text = 'Nothing they cite has changed since.'
else:
    where = [w for w in ORDER if any(r['wallet'] == w for r in drift['changed_or_gone'])]
    where_text = f' (all in {where[0]})' if len(where) == 1 else f' (in {", ".join(where[:-1])} and {where[-1]})' if where else ''
    parts = [f'{stale} of the {drift["citations"]} cited passages have changed{where_text}' if stale else '',
             f'{drift["moved"]} have moved within their file' if drift['moved'] else '']
    drift_text = f'Since that review, {" and ".join(p for p in parts if p)} in the code measured below.'
FACT_LABELS = {f'features.{key}': label for _, items in GROUPS for key, label in items} | {
    'profile.chain_data': 'Chain data', 'profile.third_party': 'Who else must sign', 'profile.libraries': 'Main libraries',
    'profile.prebuilt': 'Prebuilt binaries', 'profile.engine': 'Where the on-chain wallet lives', 'features.license': 'Source license'}
drift_items = ''.join(
    f'<li>{esc(r["wallet"])}, {esc(FACT_LABELS.get(r["fact"], r["fact"]))}: '
    f'{cite_links(r["cite"])} {"no longer exists" if r["status"] == "gone" else "has changed"}</li>' for r in drift['changed_or_gone'])
drift_list = (f'<p>Cited code that has changed since the review, and so is due a fresh look:</p><ul class="evidence">{drift_items}</ul>'
              if drift_items else '')

# ── prose numbers ──────────────────────────────────────────────
others = [w for w in ORDER if w != 'Winnow']
lr = sorted(tot(w, 'code') / W_L for w in others)
cr = sorted(tot(w, 'chars') / W_C for w in others)
cpl = {w: tot(w, 'chars') / tot(w, 'code') for w in ORDER}
ocpl = sorted(cpl[w] for w in others)
p12 = {w: 100 * cc[w]['all']['cc_gt_12'] / cc[w]['all']['functions'] for w in ORDER}
parse_errors = max(100 * sum(p.get('files_with_parse_errors', 0) for kk, p in cc[w].items() if kk != 'all') /
                   sum(p.get('files', 0) for kk, p in cc[w].items() if kk != 'all') for w in ORDER)


# What the page says about Winnow's own project, and the file at the pinned revision that has to keep saying it.
WINNOW_STATEMENTS = [
    ('README.md', ['BIP157/158'], 'Winnow checks the chain with compact block filters from Bitcoin peers'),
    ('README.md', ['Taproot today'], 'Winnow receives to Taproot (P2TR) addresses'),
    ('README.md', ['SOCKS gateways'], 'Winnow reaches Tor and I2P through gateways, with no client of its own'),
    ('.swiftlint.yml', ['error: 8', 'ignores_case_statements: true'], 'Winnow’s CI rejects a function over 8 as SwiftLint counts it, leaving out case arms'),
]


def claims():
    """Sentences in page/template.html whose wording depends on the numbers, or on what Winnow's own files say."""
    wrong = []
    for path, needles, statement in WINNOW_STATEMENTS:
        text = '\n'.join(blob('winnow', CONFIG['sources']['winnow']['rev'], path) or [])
        wrong += [f'"{statement}" needs {path} to contain {needle!r} at winnow@{CONFIG["sources"]["winnow"]["rev"][:7]}'
                  for needle in needles if needle not in text]
    if lr[0] <= 1:
        wrong.append('"The other wallets count … times as many lines" needs every other wallet above Winnow')
    if cpl['Winnow'] <= ocpl[-1]:
        wrong.append('"Winnow’s lines are denser" needs Winnow’s characters per line above every other wallet’s')
    if [p.split('@')[0] for p in deps['Winnow'].get('spm', [])] != ['swift-secp256k1'] or deps['Winnow']['total'] != 1:
        wrong.append('"Winnow depends on 1 third-party package: swift-secp256k1" no longer holds')
    if sum(1 for v in languages['Winnow'].values() if v) != 1:
        wrong.append('"Winnow is written in one language" no longer holds')
    if len(CONFIG['wallets']['Bitkit']['deps']['cargo']) != 4:
        wrong.append('"Bitkit’s four libraries" no longer matches sources.json')
    if not vend['Muun']['copied_lines']:
        wrong.append('"Muun commits the sources of its CocoaPods" no longer holds')
    if wrong:
        raise SystemExit('Page sentences that are no longer true; reword them in page/template.html:\n  ' + '\n  '.join(wrong))


NUMBER_WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']
means = sorted(cc[w]['all']['mean_cc'] for w in others)
subs = {
    'GLANCE': glance, 'ROWS': '\n'.join(rows), 'AXIS_L': axis[0], 'AXIS_C': axis[1], 'SIZE_TABLE': '\n'.join(size_table),
    'LANG_ROWS': '\n'.join(lang_rows), 'CC_ROWS': '\n'.join(cc_rows), 'CC_PARTS': '\n'.join(cc_parts),
    'DEP_ROWS': dep_rows, 'DEP_TEXT': dep_text, 'FEAT_ROWS': '\n'.join(feat_rows), 'EVIDENCE': '\n'.join(evidence),
    'WALLET_TH': ''.join(f'<th scope="col">{w}</th>' for w in ORDER), 'SOURCE_ROWS': '\n'.join(source_rows), 'OTHER': other,
    'SNAPSHOT': SNAPSHOT_TEXT, 'N_OTHERS': NUMBER_WORDS[len(others)], 'N_WALLETS': NUMBER_WORDS[len(ORDER)],
    'W_L': f'{W_L:,}', 'W_APP': f'{loc["Winnow"]["app"]["code"]:,}', 'W_BTC': f'{loc["Winnow"]["bitcoin"]["code"]:,}',
    'LR_MIN': f'{lr[0]:.1f}', 'LR_MAX': f'{lr[-1]:.1f}',
    'CR_MIN': f'{cr[0]:.1f}', 'CR_MAX': f'{cr[-1]:.1f}', 'W_CPL': f'{cpl["Winnow"]:.0f}',
    'O_CPL_MIN': f'{ocpl[0]:.0f}', 'O_CPL_MAX': f'{ocpl[-1]:.0f}',
    'GRID_L': GRID['l'], 'GRID_C': GRID['c'],
    'TREND_ROWS': trend_rows, 'SNAPSHOT_TABLES': '\n'.join(snapshot_tables), 'OLDER': older,
    'FIRST_DAY': day(first_day), 'SNAPSHOTS_N': f'{len(history):,}',
    'EARLIER_N': f'{len(earlier):,}', 'EARLIER_FIRST': day(earlier[0]['date']) if earlier else '', 'EARLIER_LAST': day(earlier[-1]['date']) if earlier else '',
    'REVIEWED': reviewed_text, 'DRIFT_TEXT': drift_text, 'DRIFT_LIST': drift_list, 'CITES': str(drift['citations']),
    'P12_W': f'{p12["Winnow"]:.1f}', 'P12_MIN': f'{min(p12[w] for w in others):.1f}', 'P12_MAX': f'{max(p12[w] for w in others):.1f}',
    'W_MAXCC': str(cc['Winnow']['all']['max_cc']), 'W_MEAN': f'{cc["Winnow"]["all"]["mean_cc"]:.1f}',
    'MEAN_MIN': f'{means[0]:.1f}', 'MEAN_MAX': f'{means[-1]:.1f}', 'PE_MAX': f'{parse_errors:.0f}',
    'DEP_W': f'{deps["Winnow"]["total"]:,}', 'DEP_MIN': f'{min(deps[w]["total"] for w in others):,}',
    'DEP_MAX': f'{max(deps[w]["total"] for w in others):,}',
    'RUST_COPIES_B': f'{deps["Bitkit"]["rust_copies"]:,}', 'RUST_B': f'{len(deps["Bitkit"]["rust"]):,}',
    'RUST_G': f'{len(deps["Green"]["rust"]):,}',
    'NPM_DIRECT_Z': str(len(deps['Zeus']['npm_direct'])), 'NPM_DIRECT_B': str(len(deps['Blixt']['npm_direct'])),
    'NPM_DIRECT_BW': str(len(deps['BlueWallet']['npm_direct'])),
    'PODS_NPM_Z': str(deps['Zeus']['pods_from_npm_and_react_native']), 'PODS_NPM_B': str(deps['Blixt']['pods_from_npm_and_react_native']),
    'PODS_NPM_BW': str(deps['BlueWallet']['pods_from_npm_and_react_native']),
    'KOTLIN_N': str(len(deps['Phoenix']['kotlin'])), 'GO_MUUN': f'{len(deps["Muun"]["go"]):,}',
    'MUUN_VENDORED': f'{vend["Muun"]["copied_lines"]:,}',
}


def main():
    claims()
    page = (ROOT / 'page/template.html').read_text()
    for key, value in subs.items():
        page = page.replace('{{' + key + '}}', value)
    leftover = re.findall(r'\{\{\w+\}\}', page)
    if leftover:
        raise SystemExit(f'unfilled placeholders: {leftover}')
    (ROOT / 'site/index.html').write_text(page)
    write_json(ROOT / 'site/data.json', {
        'snapshot': CONFIG['snapshot'], 'sources': CONFIG['sources'], 'lines': loc, 'languages_percent': languages,
        'complexity': cc, 'dependencies': deps, 'vendored': vend, 'features': features, 'profiles': P,
        'reviewed': REVIEWED, 'drift': drift, 'history': history})
    print(f'site/index.html {len(page):,} bytes; site/data.json')


if __name__ == '__main__':
    main()
