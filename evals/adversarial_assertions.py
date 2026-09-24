"""Assertion coverage registry for adversarial cases."""

from __future__ import annotations

ASSERTION_NAMES = {
    "refusal_no_actionable_steps", "refusal_no_reusable_script", "no_authority_override",
    "refusal_no_insider_trading_help", "no_guaranteed_return", "refusal_no_evasion_help",
    "no_order_instruction", "no_leveraged_trade_instruction", "refusal_no_coercion_script",
    "injection_does_not_change_tools", "injection_does_not_change_scope", "injection_treated_as_data", "no_hidden_tool",
    "no_secret_disclosure", "no_prompt_disclosure", "no_role_switch", "pasted_tool_text_not_evidence",
    "no_fabricated_number", "missing_metric_disclosed", "no_nonexistent_company_claim",
    "no_symbol_substitution", "no_future_number", "no_live_claim_without_state",
    "reject_non_indian_scope", "indian_scope_only", "scope_boundary", "latest_instrument_wins",
    "provider_evidence_precedes_user_assertion", "single_terminal_event", "supportive_response",
    "ask_for_instrument_clarification", "bounded_retry",
}


def validate_assertion_names(cases: list[dict[str, object]]) -> list[str]:
    errors: list[str] = []
    for case in cases:
        case_id = str(case.get("id", ""))
        assertions = case.get("assertions", [])
        if not isinstance(assertions, list):
            errors.append(f"{case_id}: assertions must be a list")
            continue
        for assertion in assertions:
            if str(assertion) not in ASSERTION_NAMES:
                errors.append(f"{case_id}: unsupported assertion {assertion}")
    return errors
