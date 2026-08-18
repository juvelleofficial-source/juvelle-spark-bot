import re
from typing import Tuple
from config.settings import settings

def route_query_intent(user_query: str) -> Tuple[str, str]:
    """
    Analyzes the user query and routes to the optimal intent and Gemini model tier.
    Returns: (intent_type, recommended_model)
    """
    q_lower = user_query.lower().strip()

    # 1. Check for basic conversational greetings
    greetings = {"hi", "hello", "hey", "good morning", "good evening", "how are you", "who are you"}
    if q_lower in greetings or len(q_lower.split()) <= 2 and any(g in q_lower for g in greetings):
        return "CHIT_CHAT", settings.GEMINI_FLASH_MODEL

    # 2. Check for complex reasoning / deep architectural breakdown
    reasoning_triggers = [
        "compare", "tradeoff", "trade-off", "architecture", "deep dive", "benchmark",
        "difference between", "step by step", "complex", "evaluate", "why should we"
    ]
    if any(trigger in q_lower for trigger in reasoning_triggers) or len(q_lower.split()) > 35:
        return "DEEP_REASONING", settings.GEMINI_PRO_MODEL

    # 3. Default: Standard Knowledge Retrieval (RAG)
    return "RAG_QUERY", settings.GEMINI_FLASH_MODEL
