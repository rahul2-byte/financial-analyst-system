# Graph Report - backend  (2026-04-19)

## Corpus Check
- Large corpus: 1598 files · ~2,760,039 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder, or use --no-semantic to run AST-only.

## Summary
- 2066 nodes · 5132 edges · 73 communities detected
- Extraction: 49% EXTRACTED · 51% INFERRED · 0% AMBIGUOUS · INFERRED: 2626 edges (avg confidence: 0.65)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Agent Research Nodes & Audit|Agent Research Nodes & Audit]]
- [[_COMMUNITY_Tool System & Postgres Client|Tool System & Postgres Client]]
- [[_COMMUNITY_Financial Analysis & Verification|Financial Analysis & Verification]]
- [[_COMMUNITY_News Pipeline & Market Data|News Pipeline & Market Data]]
- [[_COMMUNITY_Async Control & News Cache|Async Control & News Cache]]
- [[_COMMUNITY_SQL Repositories & Admin|SQL Repositories & Admin]]
- [[_COMMUNITY_Data Fetching & Deduplication|Data Fetching & Deduplication]]
- [[_COMMUNITY_Cache Management|Cache Management]]
- [[_COMMUNITY_Observability & Resilience|Observability & Resilience]]
- [[_COMMUNITY_Orchestration & Intent Routing|Orchestration & Intent Routing]]
- [[_COMMUNITY_Error Handling & Backoff|Error Handling & Backoff]]
- [[_COMMUNITY_Goal Nodes & Instrument Resolvers|Goal Nodes & Instrument Resolvers]]
- [[_COMMUNITY_Data Fetching Interfaces & YFinance|Data Fetching Interfaces & YFinance]]
- [[_COMMUNITY_Input Validation & Tickers|Input Validation & Tickers]]
- [[_COMMUNITY_Config Models & NLP Scoring|Config Models & NLP Scoring]]
- [[_COMMUNITY_Intelligence Decisions & Feedback|Intelligence Decisions & Feedback]]
- [[_COMMUNITY_Sector Risk & Schemas|Sector Risk & Schemas]]
- [[_COMMUNITY_Technical Indicators|Technical Indicators]]
- [[_COMMUNITY_Vector Storage & Orchestration Core|Vector Storage & Orchestration Core]]
- [[_COMMUNITY_Graph State & Deep Merging|Graph State & Deep Merging]]
- [[_COMMUNITY_Planner JSON Parsing|Planner JSON Parsing]]
- [[_COMMUNITY_Data Infrastructure Docs|Data Infrastructure Docs]]
- [[_COMMUNITY_Macro Scanners|Macro Scanners]]
- [[_COMMUNITY_Risk & Sentiment Scanners|Risk & Sentiment Scanners]]
- [[_COMMUNITY_Research Quality & Gates|Research Quality & Gates]]
- [[_COMMUNITY_Core Analysis Nodes|Core Analysis Nodes]]
- [[_COMMUNITY_SQL Engine & Scopes|SQL Engine & Scopes]]
- [[_COMMUNITY_Research Schemas|Research Schemas]]
- [[_COMMUNITY_Observability Config|Observability Config]]
- [[_COMMUNITY_Execution Architecture|Execution Architecture]]
- [[_COMMUNITY_Compatibility Facades|Compatibility Facades]]
- [[_COMMUNITY_Constants|Constants]]
- [[_COMMUNITY_Article Extraction|Article Extraction]]
- [[_COMMUNITY_Source Classification|Source Classification]]
- [[_COMMUNITY_Duplicate Detection|Duplicate Detection]]
- [[_COMMUNITY_Fundamental Scanning|Fundamental Scanning]]
- [[_COMMUNITY_Fundamental Testing|Fundamental Testing]]
- [[_COMMUNITY_Technical Scanning|Technical Scanning]]
- [[_COMMUNITY_Intelligence Testing|Intelligence Testing]]
- [[_COMMUNITY_Sector Risk Scorer|Sector Risk Scorer]]
- [[_COMMUNITY_Misc Init 1|Misc Init 1]]
- [[_COMMUNITY_Misc Init 2|Misc Init 2]]
- [[_COMMUNITY_Valuation Metrics|Valuation Metrics]]
- [[_COMMUNITY_Financial Risk Metrics|Financial Risk Metrics]]
- [[_COMMUNITY_Profitability Metrics|Profitability Metrics]]
- [[_COMMUNITY_Fundamental Flow|Fundamental Flow]]
- [[_COMMUNITY_RSI Calculation|RSI Calculation]]
- [[_COMMUNITY_MACD Calculation|MACD Calculation]]
- [[_COMMUNITY_Bollinger Bands|Bollinger Bands]]
- [[_COMMUNITY_Support & Resistance|Support & Resistance]]
- [[_COMMUNITY_Full Technical Scan|Full Technical Scan]]
- [[_COMMUNITY_Misc Init 3|Misc Init 3]]
- [[_COMMUNITY_Misc Init 4|Misc Init 4]]
- [[_COMMUNITY_Misc Init 5|Misc Init 5]]
- [[_COMMUNITY_Misc Init 6|Misc Init 6]]
- [[_COMMUNITY_Misc Init 7|Misc Init 7]]
- [[_COMMUNITY_Misc Init 8|Misc Init 8]]
- [[_COMMUNITY_Misc Init 9|Misc Init 9]]
- [[_COMMUNITY_Misc Init 10|Misc Init 10]]
- [[_COMMUNITY_Misc Init 11|Misc Init 11]]
- [[_COMMUNITY_Misc Init 12|Misc Init 12]]
- [[_COMMUNITY_Misc Init 13|Misc Init 13]]
- [[_COMMUNITY_Retry Logic|Retry Logic]]
- [[_COMMUNITY_Session Logging|Session Logging]]
- [[_COMMUNITY_Agent Mapping|Agent Mapping]]
- [[_COMMUNITY_Misc Init 14|Misc Init 14]]
- [[_COMMUNITY_SQL Core|SQL Core]]
- [[_COMMUNITY_URL Normalization|URL Normalization]]
- [[_COMMUNITY_Cache Object|Cache Object]]
- [[_COMMUNITY_Logging Dedup|Logging Dedup]]
- [[_COMMUNITY_Sentiment Analysis Node|Sentiment Analysis Node]]
- [[_COMMUNITY_Main App Entry|Main App Entry]]
- [[_COMMUNITY_Config Loader|Config Loader]]

## God Nodes (most connected - your core abstractions)
1. `PostgresClient` - 90 edges
2. `OHLCVData` - 69 edges
3. `FundamentalScanner` - 66 edges
4. `ToolDefinition` - 66 edges
5. `ToolRegistry` - 62 edges
6. `ErrorHandler` - 52 edges
7. `ToolNamespace` - 52 edges
8. `_RecordingGraph` - 49 edges
9. `build_graph()` - 48 edges
10. `Message` - 47 edges

## Surprising Connections (you probably didn't know these)
- `vector_db()` --calls--> `PgVectorStorage`  [INFERRED]
  backend/app/core/node_resources.py → backend/storage/vector/pgvector_storage.py
- `sql_db()` --calls--> `PostgresClient`  [INFERRED]
  backend/app/core/node_resources.py → backend/storage/sql/client.py
- `yf_fetcher()` --calls--> `YFinanceFetcher`  [INFERRED]
  backend/app/core/node_resources.py → backend/data/providers/yfinance.py
- `Save a batch of OHLCV data.` --uses--> `OHLCVData`  [INFERRED]
  backend/data/interfaces/storage.py → backend/data/schemas/market.py
- `Retrieve OHLCV data for a specific range.` --uses--> `OHLCVData`  [INFERRED]
  backend/data/interfaces/storage.py → backend/data/schemas/market.py

## Communities

### Community 0 - "Agent Research Nodes & Audit"
Cohesion: 0.02
Nodes (148): build_node_audit_entry(), _extract_symbols(), _normalize_errors(), summarize_node_output(), Get value from cache if not expired., ClaimVerificationResult, Validate claim-to-citation links and evidence sufficiency., verify_claims() (+140 more)

### Community 1 - "Tool System & Postgres Client"
Cohesion: 0.03
Nodes (140): PostgresClient, evaluate_health(), evaluate_profitability(), _evaluate_ratio(), evaluate_valuation(), FundamentalScanner, HealthResult, ProfitabilityResult (+132 more)

### Community 2 - "Financial Analysis & Verification"
Cohesion: 0.02
Nodes (135): BaseModel, chat_endpoint(), build_execution_input(), _news_fallback_items(), _primary_symbol_payload(), _structured_inputs(), _vector_items(), contrarian_analysis_node() (+127 more)

### Community 3 - "News Pipeline & Market Data"
Cohesion: 0.03
Nodes (98): ExaSearchConnector, BaseNewsConnector, _effective_child_publish_time(), ExaSearchConnector, _explode_portal_headlines(), _httpx_limits(), _looks_like_portal_page(), _matches_company_terms() (+90 more)

### Community 4 - "Async Control & News Cache"
Cohesion: 0.03
Nodes (77): run_parallel_with_timeout(), _build_offline_status_from_tool_evidence(), _merge_local_audit_status(), Builds OfflineStatus from tool evidence, ignoring hallucinations in submitted_ar, _store_data(), EmbeddingService, Generate embeddings for a batch of text strings., Offload the model from memory to free up RAM/VRAM. (+69 more)

### Community 5 - "SQL Repositories & Admin"
Cohesion: 0.08
Nodes (66): AdminRepository, get_session(), PostgreSQL storage client for the Financial Intelligence Platform.  This module, Create all tables if they don't exist., Context manager for database sessions.          Usage:             with client.g, Check if the database is up and running., Check if the database is up and running (agent tool version)., Upsert instrument master rows. (+58 more)

### Community 6 - "Data Fetching & Deduplication"
Cohesion: 0.03
Nodes (77): _article_dedupe_key(), _build_materialize_plan(), _build_news_cache_summary(), _build_news_chunk_metadata(), _build_news_pipeline_runner(), _canonicalize_ticker(), data_fetch_node(), _dataset_ready_from_status() (+69 more)

### Community 7 - "Cache Management"
Cohesion: 0.04
Nodes (73): Cache, cached_llm_response(), cached_tool_result(), clear_all_caches(), get_cache_stats(), _make_cache_wrapper(), Thread-safe caching for LLM responses and tool results.  This module provides: -, Decorator for caching LLM responses.      Args:         ttl: Time-to-live in sec (+65 more)

### Community 8 - "Observability & Resilience"
Cohesion: 0.03
Nodes (60): CircuitBreaker, CircuitBreakerOpen, CircuitState, get_circuit(), Circuit Breaker implementation for external service protection., Get or create a circuit breaker for a service., Raised when circuit is open and call is rejected., Circuit breaker to prevent cascading failures from external services.      State (+52 more)

### Community 9 - "Orchestration & Intent Routing"
Cohesion: 0.04
Nodes (62): Chat endpoint. If the user asks a complex question, we route it through the Orch, build_initial_graph_state(), _build_fail_closed_result(), classify_query_intent(), IntentClassificationResult, get_logger(), log_function_call(), Unified logging configuration for the Financial Intelligence Platform.  This mod (+54 more)

### Community 10 - "Error Handling & Backoff"
Cohesion: 0.08
Nodes (58): apply_backoff(), create_cleanup_updates(), error_handler_node(), ErrorAction, ErrorContext, ErrorHandler, ErrorSeverity, get_error_severity() (+50 more)

### Community 11 - "Goal Nodes & Instrument Resolvers"
Cohesion: 0.05
Nodes (63): _build_goal_audit(), _default_agents(), goal_node(), _is_broad_analysis_without_timeframe(), _is_clarification_followup(), _normalize_agents(), _normalize_ticker(), _resolve_ticker_with_llm() (+55 more)

### Community 12 - "Data Fetching Interfaces & YFinance"
Cohesion: 0.05
Nodes (47): ABC, _create_engine(), fetcher_interfaces, storage_interfaces, TextProcessor, YFinanceFetcher, market_schemas, text_schemas (+39 more)

### Community 13 - "Input Validation & Tickers"
Cohesion: 0.04
Nodes (44): Tests for input validation utilities., Test ticker validation., Empty ticker should be invalid., None ticker should be invalid., Valid ticker should pass., Ticker with suffix should pass., Ticker over 10 chars should be invalid., Test query sanitization. (+36 more)

### Community 14 - "Config Models & NLP Scoring"
Cohesion: 0.06
Nodes (43): BaseSettings, api(), API_TITLE(), API_VERSION(), AppSettings, DATABASE_URL(), DEBUG(), DEFAULT_LLM_MODEL() (+35 more)

### Community 15 - "Intelligence Decisions & Feedback"
Cohesion: 0.08
Nodes (23): evaluator_node(), _fallback_evaluation(), _memory_store(), _reprioritize_tasks(), EvaluationFeedback, IntelligenceDecision, MemoryStore, SystemIntelligenceLayer (+15 more)

### Community 16 - "Sector Risk & Schemas"
Cohesion: 0.13
Nodes (11): schemas, state, RiskLevel, RiskScore, SectorMetrics, VerificationResponse, Computes normalized risk scores (0-100) for a list of sectors., Calculates risk scores for financial sectors based on fundamental metrics.     D (+3 more)

### Community 17 - "Technical Indicators"
Cohesion: 0.12
Nodes (21): mean(), calculate_bollinger_bands(), calculate_macd(), calculate_rsi(), calculate_support_resistance(), scan(), Test full scan method., Scan should process valid data. (+13 more)

### Community 18 - "Vector Storage & Orchestration Core"
Cohesion: 0.09
Nodes (18): PgVectorStorage, Chat Router, critic_node, data_check_node, data_fetch_node, data_fetch_node, data_plan_node, evaluator_node (+10 more)

### Community 19 - "Graph State & Deep Merging"
Cohesion: 0.11
Nodes (14): merge_dicts(), Overwrites the value with the new one (standard for single fields)., Custom merge function for dicts - performs deep merge., replace_value(), Shallow merge would overwrite nested dicts - deep merge preserves them., Deep merge works for 3+ levels., Top-level keys from right override left., New keys from right are added. (+6 more)

### Community 20 - "Planner JSON Parsing"
Cohesion: 0.12
Nodes (9): Tests for planner JSON parsing., Should parse direct JSON string., Should parse JSON in markdown code blocks., Should parse JSON with text prefix., Should return None for invalid JSON., Should return None for empty string., Should return None for None input., Test JSON parsing from LLM responses. (+1 more)

### Community 21 - "Data Infrastructure Docs"
Cohesion: 0.2
Nodes (10): Data Pipeline Documentation, IStructuredStorage Interface, IVectorStorage Interface, ExaSearchConnector, NewsPipelineRunner, research_context_node, OHLCV Model, TextChunk Model (+2 more)

### Community 22 - "Macro Scanners"
Cohesion: 0.29
Nodes (6): commodity_price_scanner(), economic_indicator_scanner(), interest_rate_scanner(), Scans for current interest rates and central bank stance., Scans for a specific key economic indicator., Scans for the price of a key commodity.

### Community 23 - "Risk & Sentiment Scanners"
Cohesion: 0.29
Nodes (6): debt_load_scanner(), Scans for high volatility metrics., Scans for high debt load and leverage risks., Scans for negative sentiment alerts., sentiment_alert_scanner(), volatility_scanner()

### Community 24 - "Research Quality & Gates"
Cohesion: 0.47
Nodes (4): evaluate_research_gate(), ResearchGateResult, test_research_gate_blocks_major_claim_without_support(), test_research_gate_retries_when_source_diversity_is_too_low()

### Community 25 - "Core Analysis Nodes"
Cohesion: 0.4
Nodes (5): Fundamental Analysis Node, Health Router, LLMServiceInterface, Macro Analysis Node, Technical Analysis Node

### Community 26 - "SQL Engine & Scopes"
Cohesion: 0.83
Nodes (3): create_tables(), get_engine(), session_scope()

### Community 27 - "Research Schemas"
Cohesion: 0.67
Nodes (0): 

### Community 28 - "Observability Config"
Cohesion: 1.0
Nodes (0): 

### Community 29 - "Execution Architecture"
Cohesion: 1.0
Nodes (0): 

### Community 30 - "Compatibility Facades"
Cohesion: 1.0
Nodes (1): Compatibility facade for autonomous quality nodes.  Runtime code should prefer i

### Community 31 - "Constants"
Cohesion: 1.0
Nodes (1): Constants used across the codebase.

### Community 32 - "Article Extraction"
Cohesion: 1.0
Nodes (2): ArticleExtractor, ExtractionResult

### Community 33 - "Source Classification"
Cohesion: 1.0
Nodes (2): QualityScorer, SourceClassifier

### Community 34 - "Duplicate Detection"
Cohesion: 1.0
Nodes (2): NewsPipelineRecord, DuplicateDetector

### Community 35 - "Fundamental Scanning"
Cohesion: 1.0
Nodes (2): FundamentalScanner, research_execution_node

### Community 36 - "Fundamental Testing"
Cohesion: 1.0
Nodes (1): FundamentalScanner

### Community 37 - "Technical Scanning"
Cohesion: 1.0
Nodes (1): TechnicalScanner

### Community 38 - "Intelligence Testing"
Cohesion: 1.0
Nodes (1): SystemIntelligenceLayer

### Community 39 - "Sector Risk Scorer"
Cohesion: 1.0
Nodes (1): SectorRiskScorer

### Community 40 - "Misc Init 1"
Cohesion: 1.0
Nodes (0): 

### Community 41 - "Misc Init 2"
Cohesion: 1.0
Nodes (0): 

### Community 42 - "Valuation Metrics"
Cohesion: 1.0
Nodes (1): Evaluates Price/Earnings and Price/Book ratios.          Args:             pe_ra

### Community 43 - "Financial Risk Metrics"
Cohesion: 1.0
Nodes (1): Evaluates financial risk and debt levels.          Args:             debt_to_equ

### Community 44 - "Profitability Metrics"
Cohesion: 1.0
Nodes (1): Evaluates margins and Return on Equity.          Args:             profit_margin

### Community 45 - "Fundamental Flow"
Cohesion: 1.0
Nodes (1): Runs the full suite of fundamental evaluations on raw data.          Args:

### Community 46 - "RSI Calculation"
Cohesion: 1.0
Nodes (1): Calculates the Relative Strength Index (RSI).         Standard formula: RSI = 10

### Community 47 - "MACD Calculation"
Cohesion: 1.0
Nodes (1): Calculates the Moving Average Convergence Divergence (MACD).         MACD Line =

### Community 48 - "Bollinger Bands"
Cohesion: 1.0
Nodes (1): Calculates Bollinger Bands.         Middle Band = 20-period Moving Average

### Community 49 - "Support & Resistance"
Cohesion: 1.0
Nodes (1): Calculates Pivot Point-based Support and Resistance levels.         Based on the

### Community 50 - "Full Technical Scan"
Cohesion: 1.0
Nodes (1): Runs a full technical scan on the provided DataFrame.         Returns the latest

### Community 51 - "Misc Init 3"
Cohesion: 1.0
Nodes (0): 

### Community 52 - "Misc Init 4"
Cohesion: 1.0
Nodes (0): 

### Community 53 - "Misc Init 5"
Cohesion: 1.0
Nodes (0): 

### Community 54 - "Misc Init 6"
Cohesion: 1.0
Nodes (0): 

### Community 55 - "Misc Init 7"
Cohesion: 1.0
Nodes (0): 

### Community 56 - "Misc Init 8"
Cohesion: 1.0
Nodes (0): 

### Community 57 - "Misc Init 9"
Cohesion: 1.0
Nodes (0): 

### Community 58 - "Misc Init 10"
Cohesion: 1.0
Nodes (0): 

### Community 59 - "Misc Init 11"
Cohesion: 1.0
Nodes (0): 

### Community 60 - "Misc Init 12"
Cohesion: 1.0
Nodes (0): 

### Community 61 - "Misc Init 13"
Cohesion: 1.0
Nodes (0): 

### Community 62 - "Retry Logic"
Cohesion: 1.0
Nodes (1): Create cleanup updates for retry.          Args:             retry_count: New re

### Community 63 - "Session Logging"
Cohesion: 1.0
Nodes (1): Factory method to create a session logger.          Args:             query: The

### Community 64 - "Agent Mapping"
Cohesion: 1.0
Nodes (0): 

### Community 65 - "Misc Init 14"
Cohesion: 1.0
Nodes (0): 

### Community 66 - "SQL Core"
Cohesion: 1.0
Nodes (1): engine

### Community 67 - "URL Normalization"
Cohesion: 1.0
Nodes (1): URLNormalizer

### Community 68 - "Cache Object"
Cohesion: 1.0
Nodes (1): Cache

### Community 69 - "Logging Dedup"
Cohesion: 1.0
Nodes (0): 

### Community 70 - "Sentiment Analysis Node"
Cohesion: 1.0
Nodes (0): 

### Community 71 - "Main App Entry"
Cohesion: 1.0
Nodes (0): 

### Community 72 - "Config Loader"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **218 isolated node(s):** `Config`, `Verifies that Reciprocal Rank Fusion correctly combines results.     We'll test`, `Verifies that more recent documents get a higher score.`, `Verifies the integration of RRF and Decay in PgVectorStorage.`, `Cached decorator should cache async results.` (+213 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Observability Config`** (2 nodes): `test_observability_config.py`, `test_observability_uses_central_settings_instead_of_os_getenv()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Execution Architecture`** (2 nodes): `test_execution_architecture.py`, `test_legacy_tool_executor_wrapper_is_removed_from_runtime_path()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Compatibility Facades`** (2 nodes): `nodes.py`, `Compatibility facade for autonomous quality nodes.  Runtime code should prefer i`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Constants`** (2 nodes): `constants.py`, `Constants used across the codebase.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Article Extraction`** (2 nodes): `ArticleExtractor`, `ExtractionResult`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Source Classification`** (2 nodes): `QualityScorer`, `SourceClassifier`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Duplicate Detection`** (2 nodes): `NewsPipelineRecord`, `DuplicateDetector`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Fundamental Scanning`** (2 nodes): `FundamentalScanner`, `research_execution_node`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Fundamental Testing`** (2 nodes): `FundamentalScanner`, `test_fundamentals.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Technical Scanning`** (2 nodes): `TechnicalScanner`, `test_indicators.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Intelligence Testing`** (2 nodes): `SystemIntelligenceLayer`, `test_system_intelligence.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Sector Risk Scorer`** (2 nodes): `SectorRiskScorer`, `test_sector_risk.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 1`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 2`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Valuation Metrics`** (1 nodes): `Evaluates Price/Earnings and Price/Book ratios.          Args:             pe_ra`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Financial Risk Metrics`** (1 nodes): `Evaluates financial risk and debt levels.          Args:             debt_to_equ`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Profitability Metrics`** (1 nodes): `Evaluates margins and Return on Equity.          Args:             profit_margin`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Fundamental Flow`** (1 nodes): `Runs the full suite of fundamental evaluations on raw data.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `RSI Calculation`** (1 nodes): `Calculates the Relative Strength Index (RSI).         Standard formula: RSI = 10`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `MACD Calculation`** (1 nodes): `Calculates the Moving Average Convergence Divergence (MACD).         MACD Line =`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Bollinger Bands`** (1 nodes): `Calculates Bollinger Bands.         Middle Band = 20-period Moving Average`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Support & Resistance`** (1 nodes): `Calculates Pivot Point-based Support and Resistance levels.         Based on the`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Full Technical Scan`** (1 nodes): `Runs a full technical scan on the provided DataFrame.         Returns the latest`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 3`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 4`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 5`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 6`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 7`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 8`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 9`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 10`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 11`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 12`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 13`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Retry Logic`** (1 nodes): `Create cleanup updates for retry.          Args:             retry_count: New re`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Session Logging`** (1 nodes): `Factory method to create a session logger.          Args:             query: The`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Agent Mapping`** (1 nodes): `agent_map.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Init 14`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `SQL Core`** (1 nodes): `engine`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `URL Normalization`** (1 nodes): `URLNormalizer`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Cache Object`** (1 nodes): `Cache`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Logging Dedup`** (1 nodes): `test_logging_dedup.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Sentiment Analysis Node`** (1 nodes): `test_sentiment_analysis_node.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Main App Entry`** (1 nodes): `main.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Config Loader`** (1 nodes): `loader.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PostgresClient` connect `Tool System & Postgres Client` to `Agent Research Nodes & Audit`, `Financial Analysis & Verification`, `News Pipeline & Market Data`, `SQL Repositories & Admin`, `Observability & Resilience`, `Goal Nodes & Instrument Resolvers`, `Data Fetching Interfaces & YFinance`?**
  _High betweenness centrality (0.081) - this node is a cross-community bridge._
- **Why does `Unified application configuration package.  Public API remains compatible with p` connect `Config Models & NLP Scoring` to `Tool System & Postgres Client`, `Financial Analysis & Verification`, `News Pipeline & Market Data`, `Cache Management`, `Observability & Resilience`, `Orchestration & Intent Routing`, `Error Handling & Backoff`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `FundamentalScanner` connect `Tool System & Postgres Client` to `Technical Indicators`, `Config Models & NLP Scoring`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Are the 86 inferred relationships involving `str` (e.g. with `.search()` and `._fuse_candidates()`) actually correct?**
  _`str` has 86 INFERRED edges - model-reasoned connections that need verification._
- **Are the 51 inferred relationships involving `PostgresClient` (e.g. with `IStructuredStorage` and `OHLCVData`) actually correct?**
  _`PostgresClient` has 51 INFERRED edges - model-reasoned connections that need verification._
- **Are the 67 inferred relationships involving `OHLCVData` (e.g. with `MarketRepository` and `PostgresClient`) actually correct?**
  _`OHLCVData` has 67 INFERRED edges - model-reasoned connections that need verification._
- **Are the 64 inferred relationships involving `FundamentalScanner` (e.g. with `TestEvaluateValuation` and `TestEvaluateHealth`) actually correct?**
  _`FundamentalScanner` has 64 INFERRED edges - model-reasoned connections that need verification._