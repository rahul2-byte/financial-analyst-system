# OpenRouter-only migration plan
Delete: services/chatgpt_codex_service.py, tests/unit/test_chatgpt_codex_service.py, services/hive_service.py (renamed -> openrouter_service.py), tests/unit/test_hive_service.py (renamed -> test_openrouter_service.py)
Create: services/openrouter_service.py (adapted from hive_service: already OpenAI-compatible)
Change: config/models.py, core/resources.py, agent_loop/{model_streaming,model_events,runtime}.py, routes/health.py, events/models.py, finai/{cli,session,session_runtime,state,plain}.py, evals/*, .env.example, README, docs/*, tests
Status: done
