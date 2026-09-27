"""Render site/index.html and site/data.json from data/, features/ and wallets.json.
No number on the page is typed by hand; every citation links to the pinned revision."""
import html
import json
import re
from datetime import date

from common import CONFIG, DATA, ROOT, write_json

esc = html.escape
PROFILES = json.loads((ROOT / 'wallets.json').read_text())
ORDER = PROFILES['order']
loc = json.loads((DATA / 'loc.json').read_text())
cc = json.loads((DATA / 'complexity.json').read_text())
deps = json.loads((DATA / 'deps.json').read_text())
vend = json.loads((DATA / 'vendored.json').read_text())
features = {w: json.loads((ROOT / f'features/{w.lower()}.json').read_text())['features'] for w in ORDER}
P = PROFILES['profiles']
SNAPSHOT = date.fromisoformat(CONFIG['snapshot'])
SNAPSHOT_TEXT = f'{SNAPSHOT.day} {SNAPSHOT:%B %Y}'


def link(source, path, line=None, end=None, text=None):
    spec = CONFIG['sources'][source]
    base = spec['repo'].removesuffix('.git')
    anchor = f'#L{line}' + (f'-L{end}' if end else '') if line else ''
    shown = text or (path.rsplit('/', 1)[-1] + (f':{line}' if line else ''))
    breakable = esc(shown).replace('.', '.<wbr>').replace(':', '<wbr>:')  # wrap at names, not mid-word
    return f'<a href="{esc(base + "/blob/" + spec["rev"] + "/" + path.replace(" ", "%20") + anchor)}"><code>{breakable}</code></a>'


def cite_links(text):
    out = []
    for item in (t.strip() for t in text.split(';') if t.strip()):
        source, path, a, b = re.fullmatch(r'([a-z0-9-]+):([^:]+?)(?::(\d+)(?:-(\d+))?)?', item).groups()
        out.append(link(source, path, a, b))
    return ' '.join(out)


def name_cell(w, tag='th'):
    inner = f'<strong>{w}</strong>' if w == 'Winnow' else w
    return f'<th scope="row">{inner}</th>' if tag == 'th' else inner


def fact(value):
    if isinstance(value, dict):
        cite = f' <span class="cite">{cite_links(value["cite"])}</span>' if value.get('cite') else ''
        return esc(value['text']) + cite
    return esc(value)


# ── at a glance ────────────────────────────────────────────────
glance = '\n'.join(
    f'<tr>{name_cell(w)}<td>{fact(P[w]["built_with"])}</td><td>{fact(P[w]["engine"])}</td><td>{fact(P[w]["chain_data"])}</td>'
    f'<td>{fact(P[w]["partner"])}</td><td>{fact(P[w]["distribution"])}</td></tr>' for w in ORDER)

# ── code size chart and table ──────────────────────────────────
ROLES = [('app', 'App', 'app'), ('lightning', 'Lightning engine', 'ln'), ('bitcoin', 'Bitcoin library', 'btc')]
MAX = {'l': 450_000, 'c': 10_000_000}
TICKS = {'l': [(0, '0'), (100_000, '100k'), (200_000, '200k'), (300_000, '300k'), (400_000, '400k')],
         'c': [(0, '0'), (2_000_000, '2M'), (4_000_000, '4M'), (6_000_000, '6M'), (8_000_000, '8M')]}


def tot(w, key):
    return sum(p[key] for p in loc[w].values())


def k(n):
    return f'{n / 1000:.0f}k' if n < 1_000_000 else f'{n / 1_000_000:.1f}M'


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
            cells.append(f'<td class="lib">Not counted ({P[w]["bitcoin_library_not_counted"]})</td>')
    rel = '—' if w == 'Winnow' else f'{L / W_L:.1f}× · {C / W_C:.1f}×'
    size_table.append(f'<tr>{name_cell(w)}{"".join(cells)}<td class="num"><strong>{L:,}</strong></td>'
                      f'<td class="num">{C / 1e6:.2f}M</td><td class="num">{rel}</td></tr>')
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
    '<tr><th scope="row">Go modules, inside LND</th>' + ''.join(dep_cell(w, 'go') for w in ORDER) + '</tr>',
    '<tr><th scope="row">npm packages</th>' + ''.join(dep_cell(w, 'npm') for w in ORDER) + '</tr>',
    '<tr><th scope="row">CocoaPods from the trunk</th>' + ''.join(dep_cell(w, 'pods') for w in ORDER) + '</tr>',
    '<tr class="sum"><th scope="row">Third-party packages</th>' + ''.join(f'<td class="num"><strong>{deps[w]["total"]:,}</strong></td>' for w in ORDER) + '</tr>',
])


def vendored_text(w):
    v = vend[w]
    if not v['copied_packages']:
        return 'None'
    names = ', '.join(re.sub(r'^[^/]+/', '', p).removesuffix('.ts') for p in v['copied_packages'])
    folder = sorted({p.split('/')[0] for p in v['copied_packages']})
    return f'{v["copied_lines"]:,} lines in {", ".join(f"<code>{esc(f)}</code>" for f in folder)}: {esc(names)}'


dep_text = '\n'.join(f'<tr>{name_cell(w)}<td>{fact(P[w]["libraries"])}</td><td>{fact(P[w]["prebuilt"])}</td>'
                     f'<td>{vendored_text(w)}</td><td>{esc(P[w]["patched"])}</td></tr>' for w in ORDER)

# ── features ───────────────────────────────────────────────────
GROUPS = [
    ('Paying and receiving', [('bolt11_pay', 'Pay a BOLT 11 invoice'), ('bolt11_receive', 'Receive with a BOLT 11 invoice'),
                              ('bolt12_pay', 'Pay a BOLT 12 offer'), ('bolt12_receive', 'Receive with a reusable BOLT 12 offer'),
                              ('offline_receive', 'Receive while the app is closed'), ('lnurl', 'LNURL'),
                              ('ln_address_pay', 'Pay a Lightning address'), ('ln_address_receive', 'Your own Lightning address'),
                              ('bip353', 'Pay a BIP 353 name'), ('mpp', 'Multipath payments'), ('keysend', 'Keysend')]),
    ('Channels and routing', [('choose_peer', 'Choose your channel partner'), ('jit_channels', 'Inbound channels from a provider'),
                              ('splicing', 'Splicing'), ('anchors', 'Anchor channels'), ('local_pathfinding', 'Finds its own routes')]),
    ('Safety and recovery', [('watchtower', 'Watchtower'), ('channel_backup', 'Channel backup off the phone')]),
    ('On-chain and privacy', [('taproot', 'Taproot receive addresses'), ('multisig', 'Multisig or shared accounts'),
                              ('hw_signer', 'Hardware or external signer'), ('coin_control', 'Coin control'), ('tor', 'Built-in Tor')]),
]
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
    engines = sorted({k for k in used[w] if k != app_key}, key=list(CONFIG['sources']).index)
    extra = sorted({c['source'] for c in CONFIG['wallets'][w]['deps'].get('cargo', [])} - set(engines) - {app_key},
                   key=list(CONFIG['sources']).index)

    def src(key):
        s = CONFIG['sources'][key]
        return f'<a href="{esc(s["repo"])}/tree/{s["rev"]}"><code>{esc(s["label"])}</code></a>'
    engine_cell = ', '.join(src(k) for k in engines) or 'In the same repository'
    extra_cell = ', '.join(src(k) for k in extra) or '—'
    source_rows.append(f'<tr>{name_cell(w)}<td>{src(app_key)}</td><td>{engine_cell}</td><td>{extra_cell}</td></tr>')
other = '\n'.join(f'<li><strong>{esc(n)}</strong> {esc(t)}</li>' for n, t in PROFILES['other_approaches'])

# ── prose numbers ──────────────────────────────────────────────
others = [w for w in ORDER if w != 'Winnow']
lr = sorted(tot(w, 'code') / W_L for w in others)
cr = sorted(tot(w, 'chars') / W_C for w in others)
cpl = {w: tot(w, 'chars') / tot(w, 'code') for w in ORDER}
ocpl = sorted(cpl[w] for w in others)
p12 = {w: 100 * cc[w]['all']['cc_gt_12'] / cc[w]['all']['functions'] for w in ORDER}
parse_errors = max(100 * sum(p.get('files_with_parse_errors', 0) for kk, p in cc[w].items() if kk != 'all') /
                   sum(p.get('files', 0) for kk, p in cc[w].items() if kk != 'all') for w in ORDER)
subs = {
    'GLANCE': glance, 'ROWS': '\n'.join(rows), 'AXIS_L': axis[0], 'AXIS_C': axis[1], 'SIZE_TABLE': '\n'.join(size_table),
    'LANG_ROWS': '\n'.join(lang_rows), 'CC_ROWS': '\n'.join(cc_rows), 'CC_PARTS': '\n'.join(cc_parts),
    'DEP_ROWS': dep_rows, 'DEP_TEXT': dep_text, 'FEAT_ROWS': '\n'.join(feat_rows), 'EVIDENCE': '\n'.join(evidence),
    'WALLET_TH': ''.join(f'<th scope="col">{w}</th>' for w in ORDER), 'SOURCE_ROWS': '\n'.join(source_rows), 'OTHER': other,
    'SNAPSHOT': SNAPSHOT_TEXT,
    'W_L': f'{W_L:,}', 'W_APP': f'{loc["Winnow"]["app"]["code"]:,}', 'W_BTC': f'{loc["Winnow"]["bitcoin"]["code"]:,}',
    'W_LN': f'{loc["Winnow"]["lightning"]["code"]:,}', 'LR_MIN': f'{lr[0]:.1f}', 'LR_MAX': f'{lr[-1]:.0f}',
    'CR_MIN': f'{cr[0]:.1f}', 'CR_MAX': f'{cr[-1]:.1f}', 'W_CPL': f'{cpl["Winnow"]:.0f}',
    'O_CPL_MIN': f'{ocpl[0]:.0f}', 'O_CPL_MAX': f'{ocpl[-1]:.0f}',
    'E_PHX': f'{loc["Phoenix"]["lightning"]["code"]:,}', 'E_BITKIT': f'{loc["Bitkit"]["lightning"]["code"]:,}',
    'E_LND': f'{loc["Zeus"]["lightning"]["code"]:,}',
    'P12_W': f'{p12["Winnow"]:.1f}', 'P12_MIN': f'{min(p12[w] for w in others):.1f}', 'P12_MAX': f'{max(p12[w] for w in others):.1f}',
    'W_MAXCC': str(cc['Winnow']['all']['max_cc']), 'W_MEAN': f'{cc["Winnow"]["all"]["mean_cc"]:.1f}', 'PE_MAX': f'{parse_errors:.0f}',
    'DEP_W': f'{deps["Winnow"]["total"]:,}', 'DEP_P': f'{deps["Phoenix"]["total"]:,}',
    'DEP_MAX': f'{max(deps[w]["total"] for w in others):,}',
    'RUST_COPIES_B': f'{deps["Bitkit"]["rust_copies"]:,}', 'RUST_B': f'{len(deps["Bitkit"]["rust"]):,}',
    'NPM_DIRECT_Z': str(len(deps['Zeus']['npm_direct'])), 'NPM_DIRECT_B': str(len(deps['Blixt']['npm_direct'])),
    'PODS_NPM_Z': str(deps['Zeus']['pods_from_npm_and_react_native']), 'PODS_NPM_B': str(deps['Blixt']['pods_from_npm_and_react_native']),
    'KOTLIN_N': str(len(deps['Phoenix']['kotlin'])),
}


def main():
    page = (ROOT / 'page/template.html').read_text()
    for key, value in subs.items():
        page = page.replace('{{' + key + '}}', value)
    leftover = re.findall(r'\{\{\w+\}\}', page)
    if leftover:
        raise SystemExit(f'unfilled placeholders: {leftover}')
    (ROOT / 'site/index.html').write_text(page)
    write_json(ROOT / 'site/data.json', {
        'snapshot': CONFIG['snapshot'], 'sources': CONFIG['sources'], 'lines': loc, 'languages_percent': languages,
        'complexity': cc, 'dependencies': deps, 'vendored': vend, 'features': features, 'profiles': P})
    print(f'site/index.html {len(page):,} bytes; site/data.json')


if __name__ == '__main__':
    main()
