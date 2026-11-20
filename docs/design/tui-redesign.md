# TUI redesign: transcript-style terminal

Goal: make the FIN-AI Textual UI read like Claude Code / Codex: one calm transcript
column, a compact activity trail per answer, and a slim status line under the composer.

## Problems in the old UI

1. Every reply is followed by a raw `Run artifact: .finai/sessions/...json` line.
2. One `Sources` card is mounted per `sources.updated` event, so one reply shows 4 stacked cards.
3. The final answer body can render empty even though the run has a 2,334-char report.
4. Heavy blocks: full-width tinted user boxes, padded bordered cards, a right rail that repeats the status bar.
5. Header and footer both carry the same "complete · guided · session" status.
6. Natural-language ticker search keeps filler words (`CAN YOU HDFC THIS OR NOT`) and asks for
   clarification even when the user typed the exact company name (`HDFC BANK`).

## Design tokens

| Token | Hex | Use |
|---|---|---|
| ink | `#131312` | screen background |
| graphite | `#23211F` | composer, user prompt chip, modals |
| rule | `#2E2C29` | hairlines, scrollbar |
| paper | `#E7E4DC` | body text |
| dim | `#98948A` | metadata, activity, hints (6.1:1 on ink, 5.3:1 on graphite) |
| ledger | `#D4A55A` | brand mark, assistant bullet, spinner, focus |
| gain | `#86B98A` | verified / success |
| loss | `#D9796B` | errors / failed checks |
| warn | `#CFC66F` | partial runs (`◐`), distinct from ledger |
| faint | `#837F75` | source domains (4.7:1 on ink) |

The type is the terminal's monospace. Hierarchy comes from color and weight only.

## Layout

```
 FIN-AI  ─────────────────────────────────────── guided · cf51ae03
                                                                   
 › Can you analyse HDFC Bank and tell me if I should buy it?        <- graphite row, ledger ›
                                                                   
 ⏺ Looked up HDFCBANK on NSE                                         <- dim activity trail
   ⎿ Price history · Yahoo Finance                                  
   ⎿ Fundamentals · Upstox                                          
                                                                   
 ● Research report                                                  <- ledger ●, markdown body
   ### Executive summary ...                                       
                                                                   
   Sources  [1] Yahoo Finance · finance.yahoo.com  [2] Upstox ...    <- one block, dim, deduped
   ✓ complete · 51.4s · 2 sources                                   <- dim footer line
                                                                   
 ┃ Ask FIN-AI…                                                      <- composer, ledger left bar
   guided · claude-haiku-5.5 · session cf51ae03      / commands · F1 help
```

- No right rail by default. `F2` (or `/context`) toggles it.
- Run artifact path moves to `/artifact` (or the trace panel); never printed per reply.
- One sources block per reply, rendered once on `run.completed`, deduped.
- Activity trail: one dim line per tool step with `⎿`, updated in place, not a new card per event.

Signature: the ledger-amber `●` answer bullet and `⎿` evidence trail, so every answer shows
where its numbers came from without boxes.

## Tasks

| # | Task | Agent | Status | Output |
|---|---|---|---|---|
| 1 | Map UI code | haiku | done | (in chat) |
| 2 | TUI redesign + empty-body/duplicate-sources fix + screenshot script | sonnet | done | `backend/finai/`, `scripts/tui_screenshot.py` |
| 3 | Ticker query stopwords + exact-name match | sonnet (worktree) | done | `backend/app/core/instrument_resolution.py` |
| 4 | Screenshot review + rework | main | done | `docs/design/screenshots/` |

## Round 2 (after live use)

Library decision: stay on Textual. It is the strongest Python TUI framework. Ink (what Claude Code uses) or
ratatui (Codex) would mean rewriting the frontend in JS/Rust plus an IPC bridge to the Python runtime, for no
visual gain Textual cannot reach.

What the user sees, and what they don't:

| Show | Hide or demote |
|---|---|
| Their prompt, the answer, one sources list, a one-line footer | "Preparing research" / "Done" trails for chat replies with no tools |
| A live trail while tools run | The full trail after completion: collapse to one summary line (`/trace` or ctrl+o expands) |
| Why an answer is partial, in plain words, in the footer | Raw ids like `news:fe…`, internal disclaimers as blockquotes in the body |
| Mode and session once (status line) | Mode/session repeated in the header |

Hierarchy and color rules:
- Ledger amber only for the brand, the answer bullet, the composer bar and focus. List bullets and the `›`
  prompt chevron use dim, not amber.
- Body text in paper; bold only where the model bolds. Dim is for metadata only.
- A failed tool marks only its glyph in loss color; its text stays dim. Partial runs use a warning tone
  (`#D9B36B`-ish, distinct from ledger) and `◐`, not a green check.
- The answer text starts on the bullet's line; never a bullet alone on an empty line.
