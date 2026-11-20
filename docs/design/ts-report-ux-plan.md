# Terminal UI: report experience and UX

Status: plan, 2026-11-21. Owner: one Sonnet implementation agent; main session reviews.
Architecture and protocol: [`../frontend.md`](../frontend.md). Visual language: the colour tokens in `frontend/src/render/theme.ts`.

## 0. Goal

A finished research answer should read like a well-set analyst note in a terminal: you can see the call, the numbers behind it, how strong the evidence is, and where each claim came from. A quick glance is enough, and it rewards a slower read. Today the TS UI prints the model's markdown and a list of sources. Python already computes much richer, structured evidence that never reaches the screen.

Two rules from `AGENTS.md` apply throughout:
- **Python computes, TS draws.** Every number, direction, percentage, sparkline point and status is decided in Python and sent over the bridge. TS only lays it out and colours it. No financial maths in TS and no changes to prompts.
- **Fail closed.** If the structured data is missing or invalid, render the markdown answer exactly as now. Never invent or infer a value.

## 1. What exists today (inventory, 2026-11-21)

### Data Python already has but the UI never receives

| Data | Where | Use in UI |
|---|---|---|
| `ReportDraft`: executive_summary, key_drivers[], detailed_analysis, risks[], final_view, claims[] (importance major/supporting/minor, evidence_refs, numeric_refs), citations[] | `backend/app/core/agent_loop/publication.py:67-125`; held in runtime `last_report_result` (~`runtime.py:866`), never written out | Structured report sections, claim importance markers, citation chips |
| `EvidenceFact`: fact_id, value, unit, source_id, instrument, observed_at, quality_status, source_url | `publication.py` ~18 | Key-figures table with unit, as-of and source |
| `IndicatorMeasurement`: indicator, value, unit, direction (bullish/bearish/neutral/unavailable), strength 0–1, percentile 0–1, state, event | `backend/quant/technical_models.py` (in `TechnicalSnapshot`, with as_of and warnings) | Technical signal rows with direction badge and strength bar |
| `OHLCVData` price history | `backend/data/schemas/market.py:4-16` | Sparkline and range (points down-sampled in Python) |
| `RunCompleted.evidence_status` (limited/complete), `evidence_availability[]` (source, status available/degraded/unavailable, reason) | `backend/app/events/models.py:28-41`, `evidence.py:94-122` | Coverage meter and limitations block. **Already sent; the TS UI ignores it.** |
| CitationRecord trust_tier, freshness_score, retrieved_at | `backend/app/core/research_schemas.py:10-19` | Source freshness and trust markers |
| `LookupAnswerV1` (answered/partial/insufficient_data) | `publication.py` ~100, renderer 261-278 | Compact answer card for quick lookups |

Today `ToolCompleted` carries only a detail string. The answer arrives as `TextDelta` markdown in 64-character chunks, and `Display` carries only text, sources and flags.

### TS UI defects and gaps to fix

1. **Line wrapping:** wrapped prose continuation lines start with a space, and there is a double space before bold text at 80 columns. Ink wraps with `trim:false`, so `markdown.tsx` must word-wrap inline content itself (styled segments, greedy fill, drop break spaces). A cancelled Haiku attempt may have partly edited `frontend/src/render/markdown.tsx`; check it first.
2. **Partial flag:** `transcript.ts:255` sets `partial` for every status other than completed, including failed and cancelled runs. The footer should exclude those and name the unavailable tools. Footer target: `◐ partial · news unavailable · 12.4s · 4 tools · 6 sources`.
3. **Footer:** no source count, and no reason on failure. Cancelled runs should say so.
4. **Ctrl+O:** only expands the live trail. After a run you cannot inspect the evidence. Ctrl+O when idle should print the expanded trail of the last run as a new transcript item.
5. **Headings:** every level looks the same (ledger bold). Use h1/h2 ledger bold, h3 paper bold, h4+ dim bold.
6. **Citations:** `[n]` and `[citations: …]` are plain text that doesn't connect to sources. Render them as small chips (ledger on graphite, e.g. `¹` or `[1]`) whose numbers match the Sources list.
7. **Errors:** errors are shown raw (`Provider stream failed: rate limited`). Notices need a friendly line plus a next step (`/retry`, check the key, `/model`). The wording comes from Python `display.friendly`/`provider_notice` where it exists.
8. **Failure glyphs:** `✕` and `✗` are both used. Pick `✕` everywhere.
9. **Fake fixture:** the HDFC fixture uses sections the real prompt never produces ("Key figures", "Verdict", `[3]`). Rebuild it from the real `ReportDraft` section structure, so screenshots show what users will actually see.

## 2. Target report layout

These are mockups in ASCII; the real version is drawn with the existing theme tokens. Width adapts from 80 to 160 columns, and at 80 columns side-by-side blocks stack vertically.

```
› Analyse HDFCBANK

● Gathered evidence · 4 tools · news unavailable                 (dim; ctrl+o expands)

╭─ HDFCBANK · HDFC Bank Ltd · NSE ──────────────────────────────────────────────╮
│ ₹846.00  +1.2% 1D     ▁▂▂▃▃▄▅▅▆▇▇█  6M  ₹712 – ₹861     as of 21 Nov 15:30 IST │
│ Evidence ●●●○ 3/4 sources · limited             Stance  Constructive, wait    │
╰────────────────────────────────────────────────────────────────────────────────╯

  Summary
  HDFC Bank trades about 11% above its 200-day average with strong but stretched
  momentum; fundamentals are reasonable.  ¹ ²

  Key figures                                    value     as of        source
  P/E (TTM)                                      15.13     20 Nov       ¹
  Price / book                                    2.10     20 Nov       ¹
  Return on equity                              13.75 %    FY25         ¹

  Technical signals
  RSI 14        77.9   ▲ overbought    ▰▰▰▰▱  strong   94th pct
  MACD          4.21   ▲ bullish       ▰▰▰▱▱
  vs SMA 200   +11.0 % ▲ above         ▰▰▰▱▱
  Bollinger      —     ○ unavailable

  Key drivers
  ▸ Momentum is strong but stretched (RSI 77.9).                          ²
  ▸ Valuation in line with its 5-year range.                              ¹
  · Deposit growth steady.                                                ³   (supporting: dim marker)

  Risks and contrarian view
  ⚠ Overbought readings often precede pullbacks.                         ²
  ⚠ News coverage unavailable; sentiment not assessed.

  ┃ Final view
  ┃ Constructive on fundamentals; wait for a pullback before adding.   (ledger bar)

  Detailed analysis                                                 (normal markdown)
  …

  Evidence and limitations
  ✓ fundamentals  available   ✓ prices  available   ✓ technicals  available
  ✕ news          unavailable · provider timed out
  Data observed through 21 Nov 2026 15:30 IST

  Sources
  1  Upstox fundamentals · api.upstox.com · retrieved 21 Nov
  2  Technical snapshot · computed from Upstox candles
  3  Economic Times · economictimes.com · 2 days old

  Research and education, not personalised advice.                       (dim)
◐ partial · news unavailable · 12.4s · 4 tools · 3 sources
```

Rules:
- **Order:** read the call first, then the evidence. Header card, summary, key figures, signals, drivers, risks, final view, detailed analysis, limitations, sources, disclaimer, footer.
- **Colour has meaning, not decoration.** gain is used only for a Python-supplied positive direction or change, loss only for negative, warn for risks, partial or limited evidence, and ledger for brand, headings, the final-view bar and citation chips. All other text is paper or dim.
- **Numbers** are right-aligned in their column, with the unit after the value, and use tabular layout. The value strings are formatted in Python (currency symbol, decimals, `%`), so TS never formats money.
- **Fallbacks:**
  - Leave out any block whose data is absent. A block never shows "N/A" filler, except the explicit `○ unavailable` row for an indicator that Python marks unavailable.
  - A chat-only or lookup answer shows only a compact card (answer, limitations, sources).
  - If no structured report is present, show the current markdown answer, with the wrapping and heading fixes.
- **Streaming:** while the answer streams, show the markdown as now. When `run.finished` arrives with a structured `report`, the final committed item is the structured layout. It replaces only the live draft, never items already in scrollback. If streamed blocks were already committed to `<Static>`, append the structured card section by section and do not reprint the prose. The simplest correct option is chosen in §4.3.
- **Width:**
  - 80 columns: the card drops the sparkline to a second line, and tables keep only the value and source columns.
  - 120 columns and above: full layout.
  - Never scroll horizontally, and never wrap a table row.

## 3. Data contract changes (Python, additive)

All changes are optional fields; old clients ignore them. `PROTOCOL_VERSION` stays 1 (additive fields keep v1; see `docs/frontend.md`). Regenerate `protocol/schema/*.json` and `frontend/src/protocol/generated.ts`, and keep the goldens fresh.

3.1 **`RunFinishedParams.report: ReportView | null`**, built in `backend/finai/display.py` (or a new `backend/finai/report_view.py`) from data the runtime already holds. Expose it read-only. Do not change the agent loop's logic. If the runtime does not keep a piece of data, add the smallest accessor that returns what was already computed.
```
ReportView:
  kind: "report" | "lookup"
  instrument: {symbol, name?, exchange?} | null
  quote: {price_text, change_text?, direction?: "up"|"down"|"flat", as_of_text?} | null
  sparkline: {points: float[0..1] (≤ 48, normalised in Python), period_text, low_text, high_text} | null
  evidence: {status: "complete"|"limited", sources: [{name, status: "available"|"degraded"|"unavailable", reason?}], observed_through_text?}
  stance_text?            # short label only if the report provides one; never invented
  summary: str            # markdown
  key_figures: [{label, value_text, as_of_text?, source_ref?: int}]
  signals: [{name, value_text, direction: "bullish"|"bearish"|"neutral"|"unavailable", state_text?, strength?: float 0..1, percentile_text?}]
  drivers: [{text (markdown), importance: "major"|"supporting"|"minor", source_refs: int[]}]
  risks: [{text, source_refs: int[]}]
  final_view: str | null  # markdown
  detailed_analysis: str | null  # markdown
  limitations: str[]      # evidence limitations + data gaps
  sources: DisplaySource[] with added optional {ref: int, retrieved_text?, freshness_text?, trust?}
  disclaimer: str
```
`source_refs` and the `[[fact:…]]` and citation ids are resolved to the numbers shown in Sources, in Python. Every `*_text` field is final display text (formatted values, dates in IST with explicit units). Values are sanitised with the existing `sanitize_terminal_text` and `clean_text`.

3.2 **`RunFinishedParams.evidence_availability` and `evidence_status`** are passed through (already on `RunCompleted`). The TS footer and limitations block read them, even when `report` is null.

3.3 **Fake mode and fixtures:** `backend/finai/bridge/fake.py` and the HDFC events fixture emit a realistic `report` built from the real ReportDraft section structure, plus one partial variant (news unavailable) and one lookup variant. Goldens are regenerated.

3.4 **Tests (Python):** ReportView builder from a ReportDraft plus facts plus a TechnicalSnapshot. Fact and citation refs map to source numbers. Missing data gives null or omitted blocks, never placeholders. Raw tool ids never appear. Sanitisation is applied. Sparkline points are normalised and capped at 48.

## 4. TS work

4.1 **Fixes from §1:** wrapping (own word-wrap over styled segments), partial logic, footer source count, failure reason and cancelled label, Ctrl+O on the last run, heading hierarchy, citation chips, friendly error notices, one failure glyph.

4.2 **New components** in `frontend/src/ui/report/`. Each is pure props → Ink, coloured only through `theme.ts`, and tested at 80 and 120 columns:
- `ReportCard` (header box: instrument, quote, sparkline, evidence meter, stance)
- `KeyFigures`
- `Signals` (direction glyph ▲▼●○ plus a strength bar `▰▱`)
- `Drivers`
- `Risks`
- `FinalView` (ledger left bar)
- `EvidenceBlock`
- `SourceList` (refs, freshness)
- `CitationChip`
- `Sparkline` (maps the given 0–1 points to `▁▂▃▄▅▆▇█`, nothing else)
- `ReportView` (composes all of the above, omits empty blocks)
- `LookupCard`

4.3 **Wiring:** the reducer, transcript and store gain a `report` transcript item from `run.finished.report`. Golden parity with the Python `PresentationState` must still hold; extend the goldens if the state shape changes. Pick and document one streaming-to-final strategy from §2. Recommended: keep streaming prose in the live region only (do not commit blocks to `<Static>` while a run is active). On finish, commit `ReportView` when a report is present, or otherwise commit the markdown answer. Check the scrollback behaviour with long answers.

4.4 **Theme:** add a `faint` token for rules and borders. Add a 256-colour fallback mapping when `COLORTERM` is not truecolor.

## 5. Screenshots and acceptance

New or updated snapshot scenarios, written to `docs/design/screenshots/ts-*.png`:
- `report-full` (120 columns)
- `report-partial` (news unavailable)
- `report-80col`
- `lookup`
- `ctrl-o-last-run`
- `provider-error` (friendly notice)
- the existing 10, updated

**Accept when:**
- The global TS gate passes: `npm run typecheck && npm test -- --run && npm run build`, from `frontend/`.
- The global Python gate passes: `uv run --offline ruff check backend evals`, `uv run --offline mypy backend`, `uv run --offline pytest backend/tests --no-cov -q`.
- `npm run snapshot -- --all` writes every PNG.
- No wrapped line starts with a space. No raw tool id appears in any snapshot. NO_COLOR output has no colour sequences.
- The 80-column report has no horizontal overflow, so every line is ≤ 80 cells.
- The reviewer (main session) views `report-full`, `report-partial`, `report-80col` and `lookup` and agrees that they read like §2.

## 6. Out of scope

- Prompt or agent-loop logic changes.
- New providers.
- Changes to financial calculations, other than exposing values that are already computed.
- Interactive collapse of committed scrollback.
- Mouse support.

## 7. Tracker

| Step | Status | Notes |
|---|---|---|
| U0 fixes §1 (wrap, partial, footer, headings, glyph, errors, Ctrl+O) | done | Done after U1 (U1's data was needed for the partial footer). Footer `◐ partial · news unavailable · 12.4s · 4 tools · 3 sources`; failure/cancel wording via `describeFailure`; Ctrl+O at idle expands the last run's trail (human labels for finished tools). |
| U1 ReportView contract + builder + fake fixtures (Python) | done | `report_view.py`, `run.finished.report/evidence_*`, fixtures `goldens/reports/report-{full,partial,lookup}.json`. `stance_text` and instrument `name` are null (not derivable). Quote, sparkline and signals are real in live mode via read-only accessors and synthetic in fake mode. |
| U2 report components (TS) | done | `src/ui/report/*`; `parseReport` fails closed to the markdown answer. Tests: `test/report.test.tsx` (80/120 cols). |
| U3 wiring + streaming→final strategy | done | Strategy: nothing is committed to `<Static>` while a run is active; the draft stays in the live region inside `ClippedTail` (height-capped, head clipped). At `run.finished` we commit once: trail, then the structured report (or the markdown answer plus sources when `report` is null/invalid), then notice and footer. Why: a streamed answer cannot be swapped for a structured report once it is in scrollback. |
| U4 theme faint/256 fallback | done | `faint` token, `ansi256(n)` fallback unless COLORTERM is truecolor/24bit, NO_COLOR drops all colour (tested). |
| U5 screenshots + acceptance | done | `npm run snapshot -- --all` writes 15 PNGs incl. report-full, report-partial, report-80col, lookup, ctrl-o-last-run; the script fails on raw tool ids or lines wider than the terminal. The leading-space wrap assertion is scoped to markdown prose, because report rows use deliberate hanging indents. |
| U6 polish round | done | Sources wrap with a hanging indent (no `…`); header card border is the `faint` token (was near-invisible `rule`); markdown fallback drops unmapped raw citation ids (`[c2]`), keeps numeric `[n]`; RSI direction is decided in Python (`report_view._signals`): overbought → bearish ▼ caution, oversold → bullish ▲ (the engine's centre-50 read called RSI 74 "bullish" next to "overbought"), state text still shown. |
