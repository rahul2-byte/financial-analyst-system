# FIN-AI Technical Evaluation Report

## Scope and status

This report is derived from the tracked artifacts under `evals/gold/v1/`:

- `tasks.jsonl`: 10 contract cases.
- `baseline-results.jsonl`: 10 corresponding recorded outputs.
- `source-manifest.json`: one `synthetic_test_fixture` source, `fixture:yfinance`.

The manifest status is `seeded_fixture`, so these results validate runtime and
scoring contracts only. They are not financial-quality evidence, source-
grounded market results, or outcome claims. No live provider
run, real source snapshot, human label set, or independent judge set is saved
in this repository.

## Implemented architecture and data flow

The implemented path is:

```text
CLI / FastAPI request
  -> AgentLoop
  -> model stream and registered tools
  -> provider/replay data and deterministic quant functions
  -> typed ResearchEvent stream
  -> TUI or HTTP SSE
  -> SessionStore transcript, checkpoints, trace, and run artifacts
```

For news, the implemented path is:

```text
search connectors
  -> raw search results
  -> URL normalization and canonical resolution
  -> bounded streamed article download/extraction
  -> duplicate detection
  -> source-quality scoring/filtering
  -> NewsPipelineRecord results
```

Quantitative calculations remain in Python components under `backend/quant/`.
The model can synthesize from tool evidence, but the repository does not use
identifier matching or citation presence as proof that a source semantically
supports a claim.

## Source and data rights

The tracked gold manifest contains no source URL, retrieval timestamp, or
content hash for `fixture:yfinance`; it describes a deterministic test fixture.
The 20-case candidate manifest under `evals/candidates/pilot-v1/` likewise
keeps source URL, publisher, retrieval time, permitted-use statement, and hash
unresolved. The project owner must approve source use and freeze permitted
source bytes before those cases can become an evaluation set. That approval and
any licensing determination remain unverified.

## Evaluation protocol

`evals/run.py` joins task records to recorded result records and computes
structural metrics without contacting a provider. `evals/validate.py` checks
that the 10 task IDs and 10 result IDs match and classifies the fixture as
`synthetic_contract`. Human claim–source support is not evaluated: the saved
result set has no human labels, and the report records judge comparison as
`not_evaluated`. The offline runtime command and telemetry aggregation are
available, but no approved replay workload or telemetry artifact is saved.

The reproducible scoring command is:

```sh
PYTHONPATH=. uv run python evals/run.py \
  --mode offline \
  --tasks evals/gold/v1/tasks.jsonl \
  --results evals/gold/v1/baseline-results.jsonl \
  --manifest evals/gold/v1/source-manifest.json \
  --output /tmp/fin-ai-evaluation.json \
  --expected-cases 10 \
  --model-id fixture-model \
  --prompt-version fixture-prompt \
  --configuration-hash fixture-config
```

## Baseline results

The following values are generated from the tracked `evals/gold/v1/` artifacts
using the offline scoring path. Rates produced by `evals/metrics.py` are
case-level aggregates; the denominator for case-level rates is 10 unless noted.

| Metric | Result | Denominator / interpretation |
|---|---:|---|
| Recorded cases | 10/10 | Task and result IDs matched |
| Task completion | 10/10 | Expected terminal status matched |
| Abstention accuracy | 4/4 | Cases whose expected status required abstention |
| Fail-closed rate | 4/10 | Recorded `fail_closed` flag |
| Major-claim support rate | 0.50 | Mean of per-case structural claim-reference rates |
| Numeric provenance rate | 0.50 | Mean of per-case required-fact matching rates |
| Citation precision | 0.70 | Mean of per-case citation precision |
| Citation recall | 0.70 | Mean of per-case citation recall |
| Risk F1 | 1.00 | Mean of per-case risk F1 |
| Human claim–source support | unavailable | 0 labeled claims / 0 labeled-claim denominator |
| Judge disagreement | not evaluated | No judge labels saved |

The artifact classification is `synthetic_contract`, not `market_quality_measured`.
Evidence-selection scores are recorded as zero in the fixture output, but the
fixture does not provide a real evidence-ranking set; they should not be
interpreted as retrieval quality.

## Baseline and ablation table

`evals/ablations.py` defines paired replay variants for source-quality filtering
and report publication/reference validation. No paired ablation result files
are present under `evals/results/` beyond `.gitkeep`, so differences cannot be
computed without changing the data or inventing runs.

| Variant | Paired cases saved | Result |
|---|---:|---|
| Recorded fixture baseline | 10 | Synthetic contract metrics above |
| `quality_only` | 0 | Not measured |
| `publication_only` | 0 | Not measured |
| `full` | 0 | Not measured |

No ablation improvement is claimed.

## Latency, provider usage, and failures

No saved typed-event trace or provider telemetry artifact is available for this
workload. Therefore end-to-end p50/p95 latency, provider latency, retries,
timeouts, token usage, and verified cost are unverified. Missing telemetry is
not treated as zero.

Representative recorded outputs:

1. Success — `fixture-price-return`: terminal status `success`, numeric output
   `period_return_pct: 1.0`, citation `fixture:yfinance`.
2. Fail-closed review — `fixture-unsupported-history`: terminal status
   `needs_review`, risk `historical comparison unavailable`, forbidden claim
   type `historical valuation`.
3. Insufficient evidence — `fixture-no-evidence`: terminal status
   `insufficient_data`, risk `missing evidence`, no citations, `fail_closed:
   true`.

These are synthetic contract outputs, not financial conclusions. They are
preserved as recorded, including the negative statuses.

## Implemented features versus proposals

Implemented: deterministic quant components; typed runtime events; local
SessionStore artifacts; replay-only evaluation/runtime paths; structural report
reference validation; bounded streamed article downloads; per-session HTTP
serialization; candidate-manifest and human-label validation scaffolding.

Proposed or unverified: a frozen permitted-source benchmark; source-semantic
human labels; independent judge comparison; paired ablation results; live or
replay workload telemetry; verified provider pricing/cost; and any claim about
financial accuracy.

## Limitations and remaining verification

- The only saved baseline source is synthetic and has no real URL or source
  bytes.
- Candidate source rights, retrieval metadata, hashes, and expected evidence
  remain owner-review items.
- Human labels and adjudication are absent, so identifier validation does not
  establish semantic support.
- No saved runtime result artifacts exist for the offline runner, and no live
  provider evaluation was authorized or run.
- Cross-process session locking, if the HTTP service is deployed with multiple
  worker processes, is not verified by the process-local lock test.
- The repository CI checks validate code and fixture integrity; they do not
  establish financial-quality evidence.
