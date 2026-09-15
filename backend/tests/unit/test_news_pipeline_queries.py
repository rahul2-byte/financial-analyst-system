from data.news_pipeline.models import CompanyContext
from data.news_pipeline.query_templates import (
    QUERY_INTENT_PRIORITY,
    QueryTemplateLibrary,
    build_queries_for_company,
    derive_company_aliases,
)


def test_query_template_library_contains_all_required_intents():
    required = {
        "breaking_news",
        "earnings",
        "strategic",
        "regulatory_legal",
        "management_changes",
        "analyst_opinion",
        "competitor_context",
        "crisis_tracking",
        "background_research",
    }

    assert required.issubset(QueryTemplateLibrary.keys())


def test_build_queries_for_company_returns_india_only_query_set():
    company = CompanyContext(
        ticker="RELIANCE",
        company_name="Reliance Industries",
        nse_symbol="RELIANCE",
        bse_code="500325",
        sector="Energy",
    )

    queries = build_queries_for_company(
        company=company,
        intents=["earnings", "strategic"],
        time_window_days=30,
    )

    assert len(queries) == 4
    assert all(item["provider"] == "search" for item in queries)
    assert all("Reliance Industries" in item["query"] for item in queries)


def test_build_queries_for_company_orders_intents_by_priority():
    company = CompanyContext(
        ticker="TCS",
        company_name="Tata Consultancy Services",
        sector="IT Services",
    )

    queries = build_queries_for_company(
        company=company,
        intents=["background_research", "breaking_news", "earnings"],
        time_window_days=7,
    )

    assert queries[0]["intent"] == "breaking_news"
    assert (
        QUERY_INTENT_PRIORITY[queries[0]["intent"]]
        < QUERY_INTENT_PRIORITY[queries[-1]["intent"]]
    )


def test_derive_company_aliases_handles_legal_suffixes_and_ticker_forms():
    company = CompanyContext(
        ticker="HDFCBANK",
        company_name="HDFC BANK LTD",
        nse_symbol="HDFCBANK",
    )

    aliases = derive_company_aliases(company)

    assert "HDFC BANK LTD" in aliases
    assert "HDFC BANK" in aliases
    assert "HDFCBANK" in aliases


def test_build_queries_for_company_uses_cleaned_alias_for_legal_name():
    company = CompanyContext(
        ticker="HDFCBANK",
        company_name="HDFC BANK LTD",
        nse_symbol="HDFCBANK",
    )

    queries = build_queries_for_company(
        company=company,
        intents=["breaking_news"],
        time_window_days=30,
    )

    assert all(item["aliases"] for item in queries)
    assert any("HDFC BANK" in item["query"] for item in queries)
