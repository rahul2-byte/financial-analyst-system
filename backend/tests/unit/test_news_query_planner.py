from data.providers.news_query_planner import build_news_query_plan


def test_build_news_query_plan_returns_five_variants():
    plan = build_news_query_plan(
        objective="research the latest outlook for Apple stock",
        ticker="AAPL",
        company_name="Apple",
        timeframe="6m",
        conversation_history=[{"role": "user", "content": "Focus on growth drivers"}],
    )

    assert plan["objective"] == "research the latest outlook for Apple stock"
    assert plan["ticker"] == "AAPL"
    assert plan["company_name"] == "Apple"
    assert plan["timeframe"] == "6m"
    assert len(plan["queries"]) == 5
    assert [item["intent_type"] for item in plan["queries"]] == [
        "company_news",
        "earnings",
        "business_drivers",
        "macro_sector",
        "risks_sentiment",
    ]

    for priority, item in enumerate(plan["queries"], start=1):
        assert set(item) == {
            "intent_type",
            "query",
            "keywords",
            "preferred_domains",
            "time_range",
            "priority",
        }
        assert item["priority"] == priority
        assert isinstance(item["query"], str)
        assert item["query"]
        assert isinstance(item["keywords"], list)
        assert item["keywords"]
        assert isinstance(item["preferred_domains"], list)
        assert item["time_range"] == "m"


def test_build_news_query_plan_embeds_company_and_timeframe_context():
    plan = build_news_query_plan(
        objective="Build a stock research brief",
        ticker="HDFCBANK.NS",
        company_name="HDFC Bank",
        timeframe="1 year",
        conversation_history=[],
    )

    assert plan["timeframe"] == "1 year"
    assert len(plan["queries"]) == 5

    for item in plan["queries"]:
        assert "HDFC Bank" in item["query"]
        assert item["time_range"] == "y"


def test_build_news_query_plan_includes_objective_context_in_queries():
    plan = build_news_query_plan(
        objective="focus on loan growth and deposit trends",
        ticker="HDFCBANK.NS",
        company_name="HDFC Bank",
        timeframe="m",
        conversation_history=[],
    )

    assert len(plan["queries"]) == 5
    assert any("loan growth deposit trends" in item["query"] for item in plan["queries"])


def test_build_news_query_plan_preserves_provider_compatible_time_ranges():
    weekly_plan = build_news_query_plan(
        objective="Track recent sector news",
        ticker="AAPL",
        company_name="Apple",
        timeframe="w",
        conversation_history=[],
    )
    daily_plan = build_news_query_plan(
        objective="Track recent sector news",
        ticker="AAPL",
        company_name="Apple",
        timeframe="d",
        conversation_history=[],
    )

    assert [item["time_range"] for item in weekly_plan["queries"]] == ["w"] * 5
    assert [item["time_range"] for item in daily_plan["queries"]] == ["d"] * 5


def test_build_news_query_plan_falls_back_to_ticker_for_blank_company_name():
    plan = build_news_query_plan(
        objective="Build a stock research brief",
        ticker="HDFCBANK.NS",
        company_name="   ",
        timeframe="m",
        conversation_history=[{"role": "user", "content": "Prefer recent headlines"}],
    )

    for item in plan["queries"]:
        assert item["query"].startswith("HDFCBANK.NS ")


def test_build_news_query_plan_falls_back_to_default_subject_for_blank_ticker():
    plan = build_news_query_plan(
        objective="Build a stock research brief",
        ticker="   ",
        company_name=None,
        timeframe="m",
        conversation_history=[],
    )

    for item in plan["queries"]:
        assert item["query"].startswith("company ")
