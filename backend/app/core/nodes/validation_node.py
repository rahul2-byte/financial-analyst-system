"""Stateless validation node - validates draft report for compliance."""
import json
import logging
from typing import Dict, Any

from app.core.agent_factories import LLMServiceFactory
from app.core.prompts import prompt_manager
from app.models.request_models import Message
from quant.validators import ReportValidator

logger = logging.getLogger(__name__)


async def validation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stateless validation node - validates draft report for compliance.
    
    Uses deterministic ReportValidator for fast checks and LLM for compliance.
    """
    llm_service = LLMServiceFactory.get_llm_service()
    model = "mistral-8b"
    
    user_query = state.get("user_query", "")
    draft_report = state.get("draft_report", "")
    
    logger.info("Validation node checking compliance")
    
    try:
        # First, run deterministic checks
        validator = ReportValidator()
        check_results = validator.run_checks(draft_report)
        
        if check_results.get("is_critical_failure"):
            return {
                "final_report": None,
                "errors": check_results.get("violations", []),
            }
        
        # Use processed text (with disclaimer if added)
        processed_text = check_results.get("processed_text", draft_report)
        
        # Now use LLM for final compliance check
        messages = [
            Message(
                role="system", content=prompt_manager.get_prompt("validation.system")
            ),
            Message(
                role="user",
                content=prompt_manager.get_prompt(
                    "validation.user", user_query=user_query, draft_report=processed_text
                ),
            ),
        ]
        
        response = await llm_service.generate_message(
            messages=messages, model=model
        )
        
        # Simple validation: check if response indicates success
        # In production, you'd parse structured output
        if response.content and len(response.content) > 0:
            # Check for rejection keywords
            rejection_keywords = ["cannot approve", "failed", "violation", "not compliant"]
            is_valid = not any(kw in response.content.lower() for kw in rejection_keywords)
            
            if is_valid:
                logger.info("Validation passed, final report approved")
                return {
                    "final_report": processed_text,
                }
            else:
                logger.warning(f"Validation failed: {response.content}")
                return {
                    "final_report": None,
                    "errors": [f"Validation failed: {response.content[:200]}"],
                }
        
        # Fallback: if no response, use deterministic result
        if not check_results.get("has_violations"):
            return {"final_report": processed_text}
        
        return {
            "final_report": None,
            "errors": check_results.get("violations", []),
        }
        
    except Exception as e:
        logger.error(f"Validation node error: {e}", exc_info=True)
        return {
            "final_report": None,
            "errors": [f"Validation error: {str(e)}"],
        }
