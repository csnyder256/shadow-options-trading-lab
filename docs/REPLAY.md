# Historical exit-policy replay

## Start with the fictional demonstration

```sh
python -m atlas.options.replay_report --demo --output replay-demo
```

Open the generated `index.html` directly in a browser. The bundled XYZ inputs on 2026-07-14 are invented, not observed market data. The report executes the repository's real current and frozen V1 exit engines. It shows different exit timings, a still-open path, and a path with insufficient context. No order, broker, live feed or API key is involved.

Choose a position and engine, play or scrub its recorded marks, inspect inputs and decision state, then inspect paired closed results. The four-step keyboard-accessible tour explains replay, rule traces, coverage and provenance. Use the JSON/CSV buttons or Print/PDF. The page is self-contained and never fetches data.

## Replay recorded ledgers

```sh
python -m atlas.options.replay_report \
  --entries /path/to/entries.jsonl \
  --quotes /path/to/quotes-day-one.jsonl \
  --quotes /path/to/quotes-day-two.jsonl \
  --label "Recorded exit-policy study" \
  --fee-per-contract 0.65 \
  --output /path/to/new-report
```

Inputs are explicitly supplied, read only and limited to 20 MiB per file. The output directory must not exist, so old reports cannot be silently replaced. The generated directory contains HTML, JSON, CSV and a manifest that hashes each of the first three files. Copy it to share; no hidden database is required.

Entries and quotes use the existing `shadow_entry` and `shadow_quote` schema. Non-entry and merged entry records are excluded. Quote position IDs must match a included entry and the same OCC. Filter unrelated or merged-position quote rows before exporting your study. Timestamps must agree with the recorded New York minute, quotes must not precede entry, and duplicate timestamps, crossed NBBO, non-finite values, invalid contract quantities and partial context are rejected. Schema-1 quotes without `ext` count as missing context; they are never assigned invented engine inputs. Quotes are ordered by timestamp. Each trace ends at that engine's first SELL.

V3 probability and horizon fall back to the entry record only when their stored quote context is absent, matching the existing replay function. The report flags this fallback. It carries the same peaks, breach timers and trailing latch as the existing runner. A failed decision is a HOLD with unchanged carried state and a visible error count; reports retain the exception type without its potentially sensitive message.

## Interpret results

Fills buy at the entry ask and sell at the first SELL quote's bid, for 100 shares per contract. The configured per-contract fee is charged on both entry and exit. Closed-only sums are dollars, not portfolio returns or equity-account performance. Open positions and positions with no replayable quotes have null realized P&L and are excluded from paired dollar comparisons. The displayed realized series contains closed positions only.

This is an exit-policy replay of selected entries. It does not model entry selection, market impact, fill feasibility, liquidity, assignment, dividends or a full portfolio. Quote hashes identify the supplied bytes' canonical values; they do not establish a vendor's authenticity. An undefined internal metric is represented as null.

## Reproduce and share

The report records every consumed mark, parameter values, canonical entry and quote hashes, the product version, and SHA-256 for the replay code, both engines, their local mathematical dependencies, the viewer and requirements. Re-run with the same release, dependencies, inputs and fee to reproduce the canonical report hash. Change one of those inputs and the provenance changes.

Exports contain position IDs, OCCs, dates, quotes, decision context and calculated results. Private signal notes and configuration are excluded, but position identifiers may still reveal research. Review the exported data before sharing. HTML uses inert escaped JSON, text-only rendering and a content security policy. Spreadsheet-like labels are escaped in CSV to prevent formula execution.
