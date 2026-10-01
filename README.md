# Winnow compare

A reproducible comparison of open-source iPhone Lightning wallets, published at
**https://compare.winnowwallet.com/**.

It measures [Winnow](https://github.com/winnowwallet/winnow)'s Lightning beside the
open-source iPhone wallets that run a Lightning node on the phone (Phoenix, Bitkit, Blixt and Zeus):
features, lines of code, languages, cyclomatic complexity and CRAP, third-party dependencies,
prebuilt binaries, vendored code and patched dependencies. Every project is pinned to an exact
commit, and every number on the site comes out of `./build`.

It is measured again every day. The Daily workflow moves each pin to what the wallet ships that
day, rebuilds, and records a snapshot in `data/history.json` whenever anything moved; the page
charts each wallet's lines, packages and complex functions over time.

## Reproduce

Needs Python 3.11+, Node, Go and Cargo, and network access to GitHub, crates.io, the Go module
proxy and Maven Central.

```sh
npm ci                                # pins cloc 2.06
python3 -m pip install -r requirements.txt  # pins the tree-sitter grammars
./build                               # fetch, measure, check citations, render
git diff                              # empty when the measurement reproduces
```

`./build test|fetch|measure|evidence|render` runs one step; `test` checks the counting rules against
hand-counted cases in `tests/`. The Reproduce workflow runs the whole build
on every pull request and fails if anything it produces differs from what is committed.

## What is measured, and how

| Measure | Tool | Rule |
| --- | --- | --- |
| Lines of code | [cloc](https://github.com/AlDanial/cloc) 2.06 | Non-blank, non-comment lines in programming languages, for code that builds into the iPhone app. Characters are counted with comments and whitespace removed, so dense code is not rewarded. |
| Complexity | [tree-sitter](https://tree-sitter.github.io/) grammars | Cyclomatic complexity per function: 1 plus each `if`/`guard`, loop, non-default `case`/`when`/`match` arm, `catch`, ternary, `&&`, `\|\|`, `??` and elvis. Closures and nested functions count toward the function that contains them. |
| CRAP | from complexity | `CRAP = CC² × (1 − coverage)³ + CC`. Coverage needs each project's tests run with instrumentation (on a Mac for the Swift apps) and is not measured, so the site reports the floor CRAP cannot go below: CC. |
| Dependencies | the apps' own lockfiles | SwiftPM and CocoaPods lockfiles; npm production closures from yarn/bun lockfiles; Kotlin libraries resolved for `ios_arm64` from Maven Central metadata; Rust crates from `cargo tree --target aarch64-apple-ios`; Go modules from `go list -deps` with LND's iOS build tags. |
| Vendored code | `tools/vendored.py` | Third-party packages committed into an app's repository, counted by source (or by published build output when only that was copied), plus committed binaries and dependency patches. |
| Features | reviewed by hand | Each cell in `features/` cites the code that establishes it, at the revision in `reviewed.json`. `./build evidence` fails if a citation does not resolve there, and writes `data/drift.json`: which cited passages have changed in the code measured since. |

Excluded everywhere: tests, Android/desktop/web code, build tooling, files marked as generated
(protobuf, sqlc, UniFFI bindings) and vendored code. Rust test modules inside source files are
removed before counting. Lightning engines are counted at the version each app pins, as the named
library only.

## Layout

```
sources.json        every project, how its pin is found, its exact commit, what counts as app and
                    engine, dependency inputs
reviewed.json       the revision each hand-reviewed fact was checked against, and when
wallets.json        hand-reviewed profile facts (engine, chain data, channel partner…) with citations
features/           hand-reviewed feature cells, one file per wallet, each with code citations
locks/              a Cargo.lock for a pinned source that does not commit one
tools/              update, fetch, loc, complexity, deps, vendored, history, evidence, render
tests/              hand-counted cases that pin the counting rules, and the pin and review rules
page/template.html  the page; placeholders are filled by tools/render.py
data/               measurements, history.json and drift.json (generated, committed)
site/               the published site (generated, committed); site/data.json has everything
```

## How pins move

`./build update` (run by the Daily workflow, never by a plain `./build`) resolves every source in
`sources.json` from its `track` rule and rewrites `rev`, `label`, `version` and `date`:

| Source | Follows |
| --- | --- |
| Winnow | the `lightning` branch of winnowwallet/winnow, where Lightning is being added to the app, then `main` once it merges |
| Phoenix, Bitkit, Blixt, Zeus | the head of their default branch |
| lightning-kmp | `lightningkmp` in Phoenix's `gradle/libs.versions.toml`; the Kotlin libraries use the same catalog |
| Synonym's LDK Node, bitkit-core, Paykit, VSS client | Bitkit's `Package.resolved` |
| rust-lightning | the `lightning` version in LDK Node's Cargo.lock |
| Blixt's LND | Blixt's `bun.lock` → react-native-turbo-lnd's `lnd-source.properties` → that fork and commit |
| Zeus's LND, LDK Node, Cashu CDK | Zeus's `fetch-libraries-versions.json` |

A source that commits no Cargo.lock (Synonym's LDK Node) gets one from `cargo generate-lockfile`
when its revision changes, saved in `locks/` so the measurement stays reproducible. When anything
moved, `snapshot` becomes the day's date and `./build` adds that day's row to `data/history.json`.

What the Daily workflow cannot decide is left to fail loudly: a counted path that no longer
exists, a declared version with no matching tag, a citation that no longer resolves, or a sentence
on the page whose wording the new numbers contradict (`claims()` in `tools/render.py`). A failed
run publishes nothing; fix the config or the wording and run it again from the Actions tab.

## Re-reviewing features

Feature cells and profile facts stay pinned to the revision they were checked against, so their
links never drift. The page says how many cited passages have changed since, and lists them.
To review again:

```sh
python3 tools/evidence.py --adopt winnow   # or several sources, or none for all
```

That moves the named sources in `reviewed.json` to today's pins, follows citations whose code only
moved within its file, and lists the ones to check by hand. Fix those cells and citations, then
`./build evidence render`.

## Deploying

`.github/workflows/site.yml` and `wrangler.jsonc` deploy `site/` as a Cloudflare Worker with static
assets on every push to main that changes the site, as the [census](https://github.com/winnowwallet/census)
does. `.github/workflows/daily.yml` runs at 06:17 UTC, commits the day's snapshot to main when
anything moved, and calls the Site workflow to deploy it (pushes made with the workflow token do not
start other workflows). The Worker's custom domain, compare.winnowwallet.com, gets its DNS record and certificate from
Cloudflare on deploy. Needs the `CF_API_TOKEN` (Edit Cloudflare Workers, plus Zone → DNS → Edit on
winnowwallet.com) and `CF_ACCOUNT_ID` repository secrets.

## License

MIT. The measured projects keep their own licenses; this repository contains none of their code.
