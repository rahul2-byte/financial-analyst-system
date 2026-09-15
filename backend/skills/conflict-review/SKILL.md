---
id: conflict-review
version: 1.0.0
description: Reconcile conflicting financial evidence and preserve competing interpretations.
triggers: [conflict, conflicting, reconcile, disagreement, discrepancy, inconsistent]
inputs: [claims, sources, metric values]
outputs: [conflict register, resolution basis, unresolved conflicts]
allowed_tools: [validation:validate_data]
scripts: []
references: []
---

Do not silently choose between conflicting values. Check period, units, currency, and source quality; report unresolved conflicts and their effect on the conclusion.
