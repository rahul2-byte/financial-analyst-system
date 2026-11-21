# A5: LLM / API call layer audit (what else can cut time)

Read-only investigation. Numbers only; no prompt, response or report text was copied. Scratch scripts are in the session scratchpad (not in the repo). No network or LLM calls were made.

Scope excludes what is already being built elsewhere: concurrent tool execution, report fast path (skips the tool-selection round), skipping the Jev route call and the advisory Jev checkpoint. Constraints honoured: report content and synthesis model unchanged, no live report streaming.

## 0. Caveats that matter for every number below

- The timings in a4 (median 45.7 s) come from `zai-org/glm-5.3-flash` via provider `hive`. Hive is no longer in the code: `git log` shows "OpenRouter as the only LLM provider", `backend/app/config/models.py:10-11` defaults to `anthropic/claude-haiku-5.5` with fallback `openai/gpt-6.2-sol`, `.env` has no `OPENROUTER_MODEL`, and no `HIVE_*` setting is read by any Python file (the `HIVE_*` lines in `.env` are dead). So the GLM numbers describe the historical config. Re-measure on the current default before banking any saving.
- `.finai/model-traces/` (8 files, 29 calls) and all `.finai/evals/*/model-traces/` (485 files) are `chatgpt_codex` (`gpt-5.6-luna` / `gpt-6-luna`) only. None are GLM. They carry `chunk_timings` but no reasoning fields.
- Reasoning telemetry (`reasoning_chunk_count`, `reasoning_chars`, `openrouter_service.py:372-373, 592-596, 621-622`) is written only to `self.last_telemetry`. It is not in `provider.completed`, the event ledger, or the model trace, so it is in no artifact. I recovered the split from two places that do exist: (a) `usage.reasoning_tokens` inside the raw usage chunk of the Hive snapshots in `.finai/provider-snapshots/` (n=409 `hive/model_stream` snapshots) and (b) raw `reasoning_content` chunk char counts in the same snapshots.
- `real-v1-final-events.jsonl` (GLM, 149 completed runs) has no report-publication stage events (only the `agent` stage). It contains no repair marker, so "0 repair rounds in 149 runs" there cannot be trusted to mean the validation path ran.

## 1. Reasoning vs visible output (GLM, Hive snapshots)

Source: `.finai/provider-snapshots/*/*.json` where `provider=hive, operation=model_stream` (n=409; 169 final-synthesis-like calls = content > 800 chars and no tool call; 207 tool-selection calls = tool-call chunks present; usage has `reasoning_tokens`). Reasoning always arrives first (0 of 409 snapshots interleave reasoning after content).

| Call type | n | completion tok median | reasoning tok median | visible tok median (completion - reasoning) | reasoning share of completion (median / p10-p90 / pooled) |
|---|---|---|---|---|---|
| Final synthesis (structured report JSON) | 169 | 1,536 | 923 | 602 | 58% / 46-71% / 61% |
| Tool selection | 207 | 312 | 224 | 81 | 74% / 56-90% / 77% |
| Repair | not separable | - | - | - | no GLM repair call identified |

Cross-check by characters (all 409): final-like calls reasoning chars median 3,301 vs content chars 2,148; reasoning share of output chars median 59%. Only 9 of 178 final-like and 21 of 228 tool calls had zero reasoning chunks.

Time split, from `real-v1-final-events.jsonl` (`provider.completed.duration_ms`, `first_token_ms`; `first_token_ms` is the first visible `content` delta, so it ends when reasoning ends):

| Call type | n | duration median | first_token_ms median | duration minus first token | notes |
|---|---|---|---|---|---|
| Final synthesis (last call per run) | 144 | 32.0 s | 18.1 s (59% of call) | 11.1 s | first byte (`provider.stream.started.first_byte_ms`) median 1.06 s overall |
| Tool selection (has_tool_calls) | 162 | 7.5 s | 5.8 s (n=125; 37 calls have no visible content) | 1.6 s | |

Derived: visible generation rate = 602 tok / 11.1 s = about 54 tok/s. Reasoning time = 923 tok / 54 = about 17 s, matching TTFT minus first byte (18.1 - 1.2 = 16.9 s). So reasoning is about 17 s of the 31-32 s synthesis call (about 53%), and about 4 s of the 7.5 s tool-selection call (224 / 54 = 4.1 s). The Haiku-class default is also reasoning: OpenRouter snapshots (n=20 `anthropic/claude-haiku-5.5`) show median `reasoning_tokens` 244 of 656 completion (37%); `gpt-6.2-sol` (n=23) shows 0; `gpt-5.6-luna` (n=4) 314 of 1,660. n is small for these.

### What request parameters control reasoning

Current payload (`openrouter_service.py:321-331`) sends only `model, messages, stream, max_tokens, temperature` (+ `models`, `tools`, `tool_choice`). Nothing about reasoning is sent, so the model's default thinking is on. `ModelStreaming.stream` (`model_streaming.py:75-98`) passes `max_tokens`, `temperature=0.1`, `timeout_seconds` only. Not verifiable offline which parameter Hive's v3 endpoint honours (no docs in the repo, no network). Candidates to probe, cheapest first, each checkable from the response's `usage.reasoning_tokens` going to 0 or dropping:
- OpenRouter unified: `"reasoning": {"effort": "low"}` or `{"enabled": false}` or `{"max_tokens": N}`, optional `"exclude": true`. This is the one that applies to the current OpenRouter-only code.
- GLM/vLLM style passthroughs: `"chat_template_kwargs": {"enable_thinking": false}` or `"thinking": {"type": "disabled"}`.
- OpenAI style: `"reasoning_effort": "low"`.

A 5-call paid probe (one per candidate, tiny prompt) tells which is honoured. Needs the user's go-ahead (paid call); I did not run it.

## 2. TTFT vs generation (item 2)

Covered in section 1 table: synthesis TTFT 18.1 s / generate 11.1 s; tool selection 5.8 s / 1.6 s. Chatgpt traces have `chunk_timings` but are a different model and do not expose reasoning, so they were not used. `first_token_ms` is null for 37 of 162 tool-selection calls (pure tool-call output, no `content`). That means the TTFT metric undercounts tool-call latency; use `duration_ms` there. Prefill is small: round 1 (747 prompt tok) first byte median 0.90 s vs round 2 (3.7k prompt tok) 1.22 s, so about 0.1 ms per prompt token.

## 3. Output safety review (item 3)

- Not an extra model round, not on the report path. `runtime.py:347` sets `review_enabled` when the decision provider has `review_output`; `:534` makes `review_gate = not structured_output and review_enabled`; `:664` runs `provider.review_output` only when `not assistant.tool_calls and not structured_output and review_enabled`. Reports and lookups (`answer_contract` of `report` or `lookup`) are structured, so the review never runs for them. Nothing to skip or overlap for the report case.
- For freeform answers it is one HTTP call to the Jev decisions endpoint (`jev_service.py:294`, `timeout_seconds=10`, no retry loop in `review_output`) that blocks release of the held text (`:714-724`). Its duration is not recorded in any artifact (Jev traces are not in `.finai/model-traces`). It cannot overlap with generation because it needs the full text. Only possible overlap: none worth building.

## 4. Repair rounds (item 4)

Hard data exists only for the other provider and for a handful of live sessions:

| Source | n | Result |
|---|---|---|
| GLM `real-v1-final-events.jsonl` | 149 runs | round patterns: `TF` 131, `TTF` 12, `TxxF` 4 (`x` = provider.failed), `TTxxF` 1. No `FF` (no extra no-tool round) so no repair visible, but see caveat in section 0 |
| `chatgpt_codex` evals, repair detected by the "Formatting repair required" system message in `call.started` | gpt-full-first 150 runs: 124 with >=1 repair, 16 with 2; gpt-full-final 151: 108, 29; gpt-full-repair-final 150: 76, 28 | repair call duration median 13.4 / 12.1 / 11.7 s (n=140/136/104); an extra full model call, not a patch |
| Live session events `check.stage` | 4 runs with a failing check, all 4 retried (8 retry events) | reasons recorded: `report is not valid contract JSON` x3, `A citation did not match a verified source.` x2, `reviewer requested a rewrite` x1 (freeform safety review) |
| `.finai/logs/finai.log` "publication validation failed" | 11 warnings | reason codes (a warning can carry several): `citation_source_missing` 6, `numeric_fact_missing` 5, `claim_citation_missing` 3, `numeric_fact_source_missing` 3, `numeric_fact_reference_missing` 1, `numeric_claim_unbound` 1, `degraded_source_claim` 1 |

So repairs are common on gpt (51-83% of runs, mostly one repair at about 12 s) and unmeasured on GLM. Most triggers are deterministic bookkeeping, not wrong analysis: citation ids that do not match a verified source (`publication.py:212, 304`), numeric facts not linked to a claim or source (`:238-252, 324-361`), and invalid JSON. The repair prompt (`prompts.yaml:42-43`) already lists the unreferenced fact ids and is a full regeneration (max_tokens 8192, timeout 120 s, `runtime.py:1012-1089`, config `OPENROUTER_MAX_REPORT_REPAIRS=2`).

## 5. HTTP layer (item 5)

- Client reuse: yes. One `httpx.AsyncClient` per `OpenRouterService` (`openrouter_service.py:237-247`), built once in `resources.py:88`, Jev has its own client (`jev_service.py:105`, bare `httpx.AsyncClient()`; per-request `timeout=self.timeout_seconds` at `:166`, `:339`). `Limits` sets max connections 10 / keepalive 10 but not `keepalive_expiry`, so httpx's 5 s default applies: any gap over 5 s between LLM calls closes the connection and the next call pays DNS + TCP + TLS again. HTTP/2 is not enabled (`h2` is not installed; `httpx` 0.28.1). With sequential calls to one host, HTTP/2 multiplexing would not help; skip.
- Connect failures cost real time. `real-v1-final-events.jsonl`: 22 `provider.retrying` events, all `ConnectTimeout` (connect timeout is 5.0 s, `OPENROUTER_CONNECT_TIMEOUT`, `models.py:34`); 15 in round 1 (cold connection after idle), 6 in round 2, 1 in round 3. Calls that needed 2 attempts: round-1 duration median 13.4 s vs 7.0 s with 1 attempt (+6.4 s); round-2 50.1 s vs 29.6 s (n=4). Backoff itself is tiny (retry delay 15-746 ms), so the cost is the 5 s connect wait.
- Run-level effect: 126 clean runs median 44.5 s, p90 81.8 s; 18 runs with retry only: median 55.0 s (+10.5 s), p90 104.2 s; 5 runs with a `provider.failed`: median 101.4 s. 11 `provider.failed` events (6 transport `TimeoutError` after ~98 s with `partial_output=true`, 5 stream-phase). These drive the p90, not the median.
- Read timeout 60 s (`OPENROUTER_READ_TIMEOUT`), total budget 600 s, but run budget `max_run_seconds=150` bounds a run; a stalled stream burns up to 60 s of silence before retry.
- All provider calls in the loop are async (`async with self._client.stream`); the only sync work on the loop is the archive/trace writes at call end (see item 8).

## 6. Prompt size and caching (item 6)

- Prompt tokens (`usage.prompt_tokens`, `real-v1-final-events.jsonl`): final call median 3,726 (n=149, p90 6,086); tool-selection 747 (median, p90 1,129). So tool results plus tool-call message add about 3.0k tokens at the median.
- Cost of that prompt is small: about 0.1 ms/token (round 1 vs round 2 first-byte difference above), so about 0.3 s for the 3k tokens. Trimming tool results by half would save roughly 0.15 s. Not worth the grounding risk.
- Caching already works server-side without any request field: `usage.prompt_tokens_details.cached_tokens` is present in Hive responses, nonzero in 85 of 178 final-like and 136 of 228 tool-selection snapshots, values in 256-token steps (256, 512, 640, 704, 1024, 1088, 1280). Share of prompt tokens served from cache: 8% for final calls, 36% for tool-selection. Adding `cache_control` would not change the median meaningfully since prefill is about 0.3 s total.
- `_tool_message_content` caps tool results at 7,500 chars (`runtime.py:2305`) and, above that, replaces the payload with a summary (so oversize results already lose detail; that is a fidelity concern, not a speed one).

## 7. Remaining serial LLM calls (item 7)

Inventory of model-ish calls per report: Jev route (`routing_policy.py:129`), model rounds, Jev checkpoint (`runtime.py:~1414`), repair rounds. Already handled by the other agent: route, checkpoint, tool-selection round. No title, summary or memory-compaction LLM call exists (`context_budget.py` is deterministic; `session_store.py:267-283` titles are string slices). The freeform review is the only other LLM-ish call (section 3). After the other agent's work, a clean report is: one synthesis call. Overlap candidates therefore reduce to: connection pre-warm (section 5) running while tools fetch.

## 8. Ranked optimizations

Baseline for "median report" after the other agent's fast path: about 45.7 - 7.4 (selection round) - Jev calls = about 38 s, of which the synthesis call is about 31 s.

| # | Change | File:line | Est. saving per median report (arithmetic) | Changes report content? | Risk |
|---|---|---|---|---|---|
| 1 | Cap or lower reasoning on the final synthesis call (e.g. `reasoning: {effort: low}` or provider equivalent), applied only after an A/B | add passthrough at `openrouter_service.py:321-331`; set per round at `model_streaming.py:75-98` | Off: 923 tok / 54 tok/s = 17 s (TTFT check 18.1 - 1.2 = 16.9 s). Halved: about 8.5 s. | Possibly yes (the model thinks less before filling the schema). User says content must not change, so treat as opt-in until an A/B on about 20 prompts shows equal grounding pass rate, equal repair rate, same terminal status | Medium-high: more repairs would give back time (a repair is about 12 s on gpt; break-even if repair rate rises by more than about 17 / 12 per run) |
| 2 | Reasoning off for tool-selection and extra tool rounds (these only choose tools) | same two places, gated on "no tool messages yet or tool-result rounds that may call tools" (`model_streaming.py:82-96`) | 224 tok / 54 = about 4.1 s per round (7.5 s call). After the fast path removes round 1 for reports it saves about 0 at the median; extra tool rounds occur in 13/149 runs (9%) so mean about 0.4 s. Before the fast path: 4.1 s | No (tool choice only; verify tool set unchanged on the eval corpus) | Low |
| 3 | Deterministic post-fix for the common validation failures before spending a repair round: drop/remap citation ids that match no verified source, append missing `[[fact:ID]]` markers and `numeric_refs` for unreferenced facts, retry JSON parse after trimming fences/trailing text | `publication.py:212, 238-252, 304, 324-361`; trigger at `runtime.py:~1012-1089` | Repairs: gpt 51-83% of runs, median 12 s each. Mean saved if half are fixed deterministically: 0.5 x 0.66 x 12 = about 4 s mean. GLM rate unmeasured. Median report likely 0 (most runs have no repair) | Only by removing or relinking invalid citations that the repair would also have changed; must never add facts | Medium (AGENTS.md: preserve fail-closed behavior; only drop or relink, never invent) |
| 4 | Repair rounds with reasoning off, plus keep `max_tokens=8192` but lower repair timeout 120 s to about 45 s | `model_streaming.py:75-98`, `models.py:47` | If a repair carries 60% reasoning like synthesis: about 12 s x 0.6 = 7 s per repair; mean 0.66 x 7 = 4.6 s on gpt-like rates. Timeout cut saves tail only | No (instruction is already mechanical) | Low-medium |
| 5 | HTTP: connect timeout 5 s to 2 s, `keepalive_expiry` 60 s, pre-warm one connection at bridge start / run start (overlaps with tools) | `openrouter_service.py:237-247`, `models.py:34`, `jev_service.py:105`, `resources.py:88` | 22 ConnectTimeouts / 149 runs x 3 s = 0.44 s mean; retry-only runs cost +10.5 s x 18/149 = 1.27 s mean. Median 0 (the median run has no retry). Cuts p90 | No | Low |
| 6 | Persist `usage.reasoning_tokens`, `cached_tokens`, `reasoning_chars` on `provider.completed` and add a repair marker event | `openrouter_service.py:~621-655`, `ProviderCompleted` event in `model_streaming.py:130-` | 0 s directly; required to measure 1-4 on the real config | No | Low |
| 7 | Move `provider_archive.store` and trace fsync off the loop (`to_thread`), drop `indent=2` | `provider_archive.py:45-47`, `openrouter_service.py:637`, `model_call_trace.py:63-84` | Archive payload about 370 kB per final call; `json.dumps(indent=2)` measured 3 ms median, 15 ms max; plus hash and file write: under 0.05 s per call | No | Low |
| 8 | Trim tool result payloads | `runtime.py:2305` | 3k prompt tokens x 0.1 ms = 0.3 s; trimming half = 0.15 s | No if lossless, but grounding refs are risky | Not recommended |
| 9 | `cache_control` / HTTP2 / prompt reordering | `openrouter_service.py:321` | About 0 (server-side prefix caching already hits; prefill is about 0.3 s per 3k tokens) | No | Not recommended |

Items with no gain: output review on reports (not run), title/summary/compaction LLM calls (none exist), prompt caching and HTTP2.

## 9. Bottom line

The only call-layer lever that is large (about 17 s of the 31 s synthesis call) is reasoning effort on the final call (#1). It is the one item that may alter report content, so it should not ship without an A/B on grounding, repair rate and terminal status; everything else that is content-neutral is small at the median (#2 after fast path 0 s, #5 0 s median / 0.4-1.3 s mean, #7 under 0.1 s) or tail-only. The largest content-neutral gain is cutting repair rounds (#3, #4, about 4-5 s mean where repairs are as frequent as in the gpt evals), but their GLM/Haiku rate is unmeasured, so do #6 first and measure on the current OpenRouter default (anthropic/claude-haiku-5.5), where reasoning is 37% of completion tokens (n=20) rather than GLM's 58-61%.
