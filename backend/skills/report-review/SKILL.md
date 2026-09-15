---
id: report-review
version: 1.0.0
description: Perform a final quality and compliance review of a finance report before delivery.
triggers: [audit, verify, validate, review, quality, compliance, final]
inputs: [draft report, evidence records, citations]
outputs: [validation result, corrections, limitations]
allowed_tools: [validation:validate_report, validation:validate_data]
scripts: []
references: []
---

Check numerical consistency, citation coverage, dates, units, unsupported claims, and financial-advice boundaries. Return corrections or a clear reason a draft cannot be trusted.
