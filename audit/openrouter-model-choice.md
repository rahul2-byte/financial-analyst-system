# OpenRouter model choice for FIN-AI (as of 2026-11-20)

Status: partly verified. A figure is "unverified" when it did not appear on a page we fetched. Research used 15 web calls. Six slugs from the rankings page returned 404, and WebSearch was not available, so benchmarks were not checked.

## Candidates

| # | OpenRouter id | In $/1M | Out $/1M | Context | Tools | Latency/throughput | Source |
|---|---|---|---|---|---|---|---|
| 1 | deepseek/deepseek-v4.1-flash-1017 | 0.15 (DeepSeek direct; provider range 0.03-0.60) | 0.60 (direct; range 0.25-2.40) | unverified | Y (tools in request fields) | unverified | https://openrouter.ai/deepseek/deepseek-v4.1-flash-1017 |
| 2 | z-ai/glm-5.3-flash | 0.15 (Z.ai direct; range 0.0399-0.225) | 0.50 (direct; range 0.078-0.75) | unverified | Y (tools in request fields) | unverified | https://openrouter.ai/z-ai/glm-5.3-flash |
| 3 | openai/gpt-5-mini | 0.25 (OpenAI direct; other providers 0.25-0.275) | unverified (provider range 1.00-2.20; OpenAI line not isolated) | unverified | Y (tools field listed) | unverified | https://openrouter.ai/openai/gpt-5-mini |
| 4 | google/gemini-4-neon | 3.00 (base; provider range 1.50-5.40) | 15.00 (base; provider range 7.50-27) | 1,050,000 | Y (tools field listed) | unverified | https://openrouter.ai/google/gemini-4-neon ; https://openrouter.ai/models?supported_parameters=tools |
| 5 | anthropic/claude-opus-5.5 | 4.00 (Anthropic; others 4.00-4.40) | 20.00 (Anthropic; others 20-22) | unverified | Y (tools in request fields) | unverified | https://openrouter.ai/anthropic/claude-opus-5.5 |
| 6 | qwen/qwen3.8-27b-20260814:nitro | unverified | unverified | unverified | unverified | 511 tok/s (Cerebras, :nitro variant) | https://openrouter.ai/rankings |

Notes: the deepseek :nitro throughput (497 tok/s) applies to a different id and is not used above. Slugs claude-sonnet-5.5-20260928, claude-haiku-5.5-20261007, kimi-k3-20260715, gemini-4-carbon-20261110 and deepseek-v4.1-flash-20261017 returned 404 and are excluded. Tool support is inferred from the request-field lists on each page, not from a stated capability.

## Estimated cost per user question

Assumption: 5 calls x (15,000 in + 1,500 out) = 75,000 in + 7,500 out tokens.
Cost = (75,000 x in$/1M + 7,500 x out$/1M) / 1,000,000

- deepseek-v4.1-flash-1017: (75,000 x 0.15 + 7,500 x 0.60) / 1e6 = (11,250 + 4,500) / 1e6 = $0.0158
- z-ai/glm-5.3-flash: (11,250 + 3,750) / 1e6 = $0.0150
- openai/gpt-5-mini: input part 75,000 x 0.25 / 1e6 = $0.0188; output unverified, so total unverified
- google/gemini-4-neon (base prices): (225,000 + 112,500) / 1e6 = $0.3375
- anthropic/claude-opus-5.5: (300,000 + 150,000) / 1e6 = $0.45

Costs use list prices only. They ignore caching and provider routing, and assume each call re-sends the full 15k input.

## Recommendation

(a) Best value default: deepseek/deepseek-v4.1-flash-1017, about $0.016 per question. It is the cheapest candidate with a verified price and tool support. Its context and latency are unverified, so test before committing.

(b) Cheap fallback: z-ai/glm-5.3-flash, about $0.015 per question. It is on a different vendor, which covers outages. openai/gpt-5-mini is the alternative once its output price is confirmed (input $0.25 is verified).

(c) Premium: google/gemini-4-neon, about $0.34 per question. Tool support and a 1.05M context are verified. Claude Opus 5.5 costs $0.45 per question and was not shown to beat it on tool use.

Quality: no tool-calling benchmark was verified. The rankings page shows an Artificial Analysis index of 61.4 for Gemini 4 Neon (Xhigh), but this is unchecked.

## Next steps before choosing

1. Check context length and throughput for the top two on the OpenRouter models API or the provider pages.
2. Run a 1-hour smoke test: the same 3 tool-calling prompts on each of the 3 finalists. Check that numbers are copied exactly from tool results, time to finish against 60 s, and the number of rounds.
3. Confirm the output price for gpt-5-mini before using it as a fallback.

## Main-session verification (OpenRouter public API `GET /api/v1/models`, 2026-11-20)
The prices above are confirmed: deepseek-v4.1-flash-1017 $0.15/$0.60, gemini-4-neon $3/$15, gpt-5-mini $0.25/$2.00.
glm-5.3-flash is now $0.0399/$0.0784. The research missed two strong candidates:

| id | in $/1M | out $/1M | ctx | tools | $/question (75k in + 7.5k out) |
|---|---|---|---|---|---|
| openai/gpt-5.6-luna | 0.20 | 1.20 | 1.05M | Y | $0.024 |
| anthropic/claude-haiku-5.5 | 0.10 | 0.50 | 1M | Y | $0.011 |
| deepseek/deepseek-v4.1-flash-1017 | 0.15 | 0.60 | 1.05M | Y | $0.016 |
| anthropic/claude-sonnet-5.5 (premium) | 2.00 | 10.00 | 1M | Y | $0.225 |
| z-ai/glm-5.3-flash | 0.04 | 0.08 | 1.05M | Y | $0.004 |

Decision:
- **Default:** openai/gpt-5.6-luna, the model the prompts and evals were built around.
- **Fallbacks:** anthropic/claude-haiku-5.5, then deepseek/deepseek-v4.1-flash-1017.
- **Premium option:** anthropic/claude-sonnet-5.5.
- glm-5.3-flash is rejected: in usage tests every synthesized answer it produced failed or timed out.
- Confirm with a 3-question live smoke test per model after the migration.
