# ORCHESTRATION RULES

The Orchestrator is deterministic and controls execution order.

Rules:

- Agents must not self-trigger.
- No agent-to-agent direct calls.
- Workflow must be registry-driven.
- No hidden state between runs.
- All pipeline steps must log execution time.

New workflows must be added via workflow registry.
