# Winnow compare

A reproducible comparison of open-source iPhone Lightning wallets, published at
**https://compare.winnowwallet.com/**.

It measures [Winnow](https://github.com/winnowwallet/winnow)'s Lightning research beta beside the
open-source iPhone wallets that run a Lightning node on the phone (Phoenix, Bitkit, Blixt and Zeus):
features, lines of code, languages, cyclomatic complexity and CRAP, third-party dependencies,
prebuilt binaries, vendored code and patched dependencies. Every project is pinned to an exact
commit, and every number on the site comes out of `./build`.

## Reproduce

Needs Python 3.11+, Node, Go and Cargo, and network access to GitHub, crates.io, the Go module
proxy and Maven Central.

```sh
npm ci                                # pins cloc 2.06
python3 -m pip install -r requirements.txt  # pins the tree-sitter grammars
./build                               # fetch, measure, check citations, render
git diff                              # empty when the measurement reproduces
```

`./build fetch|measure|evidence|render` runs one step. The Reproduce workflow runs the whole build
on every pull request and fails if anything it produces differs from what is committed.

## What is measured, and how

| Measure | Tool | Rule |
| --- | --- | --- |
| Lines of code | [cloc](https://github.com/AlDanial/cloc) 2.06 | Non-blank, non-comment lines in programming languages, for code that builds into the iPhone app. Characters are counted with comments and whitespace removed, so dense code is not rewarded. |
| Complexity | [tree-sitter](https://tree-sitter.github.io/) grammars | Cyclomatic complexity per function: 1 plus each `if`/`guard`, loop, non-default `case`/`when`/`match` arm, `catch`, ternary, `&&`, `\|\|`, `??` and elvis. Closures and nested functions count toward the function that contains them. |
| CRAP | from complexity | `CRAP = CC² × (1 − coverage)³ + CC`. Coverage needs each project's tests run with instrumentation (on a Mac for the Swift apps) and is not measured, so the site reports the floor CRAP cannot go below: CC. |
| Dependencies | the apps' own lockfiles | SwiftPM and CocoaPods lockfiles; npm production closures from yarn/bun lockfiles; Kotlin libraries resolved for `ios_arm64` from Maven Central metadata; Rust crates from `cargo tree --target aarch64-apple-ios`; Go modules from `go list -deps` with LND's iOS build tags. |
| Vendored code | `tools/vendored.py` | Third-party packages committed into an app's repository, counted by source (or by published build output when only that was copied), plus committed binaries and dependency patches. |
| Features | reviewed by hand | Each cell in `features/` cites the code that establishes it. `./build evidence` fails if any citation no longer resolves at the pinned revision. |

Excluded everywhere: tests, Android/desktop/web code, build tooling, files marked as generated
(protobuf, sqlc, UniFFI bindings) and vendored code. Rust test modules inside source files are
removed before counting. Lightning engines are counted at the version each app pins, as the named
library only.

## Layout

```
sources.json        every project, its exact commit, what counts as app and engine, dependency inputs
wallets.json        hand-reviewed profile facts (engine, chain data, channel partner…) with citations
features/           hand-reviewed feature cells, one file per wallet, each with code citations
locks/              a Cargo.lock for a pinned source that does not commit one
tools/              fetch, loc, complexity, deps, vendored, evidence, render
page/template.html  the page; placeholders are filled by tools/render.py
data/               measurements (generated, committed)
site/               the published site (generated, committed); site/data.json has everything
```

## Updating

1. Move a project forward by changing its `rev` (and `label`) in `sources.json`.
2. `./build`, then review `git diff data/` — the package lists show exactly what was added or removed.
3. Re-check the feature cells and profile facts that the change could affect, and update their
   citations; `./build evidence` catches citations that moved.

## Deploying

`.github/workflows/site.yml` and `wrangler.jsonc` deploy `site/` as a Cloudflare Worker with static
assets on every push to main that changes the site, as the [census](https://github.com/winnowwallet/census)
does. The Worker's custom domain, compare.winnowwallet.com, gets its DNS record and certificate from
Cloudflare on deploy. Needs the `CF_API_TOKEN` (Edit Cloudflare Workers, plus Zone → DNS → Edit on
winnowwallet.com) and `CF_ACCOUNT_ID` repository secrets.

## License

MIT. The measured projects keep their own licenses; this repository contains none of their code.
