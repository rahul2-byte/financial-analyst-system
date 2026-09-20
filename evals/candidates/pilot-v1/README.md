# Pilot v1 candidate evaluation set

This directory is a candidate-case manifest, not a frozen benchmark and not financial-quality evidence. It contains no real source URLs, source bytes, content hashes, retrieval timestamps, permitted-use grants, expected evidence spans, or human labels.

## Project-owner actions

1. Select permitted public sources for each case and confirm that their use is allowed for local evaluation.
2. Retrieve the source bytes and call `freeze_snapshot(...)` for each approved source.
3. Replace the unresolved source fields in `cases.jsonl` with the returned source identifier, URL, publisher, retrieval time, permitted-use statement, and SHA-256 hash.
4. Define the expected evidence spans and any deterministic acceptance criteria. Do not write labels based only on the question.
5. Approve the labeling instructions and reviewer independence protocol before collecting labels.

## Independent-reviewer actions

1. Each reviewer labels every case independently using the approved source snapshot, recording evidence spans and a support, contradiction, or insufficient-evidence judgment.
2. Reviewers must preserve uncertainty and must not infer semantic support from matching identifiers, URLs, or hashes.
3. The project owner must adjudicate disagreements and retain both original labels plus the adjudication record.
4. Run `validate_human_labels(...)` before promoting labels into a frozen evaluation artifact.

Promotion requires all source metadata, content hashes, expected evidence, and independent labels to be present and validated. Until then, this manifest must remain classified as `candidate` and must not be used to claim benchmark quality, financial correctness, or model performance.
