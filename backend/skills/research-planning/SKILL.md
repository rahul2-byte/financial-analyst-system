---
id: research-planning
version: 1.0.0
description: Turn an ambiguous finance question into a bounded objective, scope, evidence plan, and approval question.
triggers: [plan, research, investigate, analyze, analysis, compare, explain, assess]
inputs: [user question, conversation context]
outputs: [research objective, scope, evidence requirements, clarification]
allowed_tools: [interaction:ask_user]
scripts: []
references: []
---

Resolve entity, timeframe, comparison basis, and desired decision. Ask one concise clarification when a missing detail materially changes the work. Do not expose private reasoning.
