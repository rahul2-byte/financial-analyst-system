# FIN-AI module map

| Area | Owns | Does not own |
|---|---|---|
| `finai/cli.py` | argument parsing, startup, cleanup | research logic |
| `finai/session.py` | compatibility facade and coordination | widget layout |
| `finai/session_persistence.py` | persistence delegation | storage schema |
| `finai/session_runtime.py` | AgentLoop construction and streaming | rendering |
| `finai/app.py` | Textual lifecycle and widget mutation | providers and quant math |
| `app/core/agent_loop/` | bounded model/tool loop and events | terminal rendering |
| `app/core/tools/` | tool catalog and execution | prompting |
| `app/core/graph/` | legacy LangGraph runtime | default CLI orchestration |
| `agents/` | specialist research nodes | provider transport |
| `data/` | fetch, validate, normalize, provenance | synthesis decisions |
| `quant/` | deterministic indicators and scans | LLM reasoning |

Start changes at the boundary that owns the side effect. Keep pure
transformations separate from filesystem, network, and UI operations.
