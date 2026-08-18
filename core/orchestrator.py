import logging
from typing import Iterator, Dict, Any, List, Optional
from memory.short_term_memory import memory_manager
from memory.long_term_memory import get_user_profile
from retrieval.vector_retriever import retrieve_hybrid_context
from core.failover_client import failover_client
from core.router import route_query_intent
from config.settings import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an Enterprise AI Assistant powered by Google Gemini and an Apache Spark Distributed Knowledge Ingestion Engine.

Your core objectives:
1. Provide accurate, clear, and highly practical answers grounded in the provided retrieved enterprise knowledge.
2. Always cite your sources when referencing facts from the retrieved knowledge chunks (e.g. [DOC_001]).
3. Personalize your response naturally if user profile preferences are present.
4. Maintain a professional, concise, and helpful tone.
5. When relevant facts are missing from retrieved documents, state clearly that information is not available in the ingested database rather than hallucinating.
"""

def build_grounded_prompt(
    user_query: str,
    conversation_history: List[Dict[str, Any]],
    retrieved_chunks: List[Dict[str, Any]],
    user_profile: Optional[Dict[str, Any]] = None
) -> str:
    """
    Constructs the grounded prompt incorporating conversation history, long-term profile, and retrieved knowledge chunks.
    """
    prompt_parts = []

    # 1. Long-Term User Profile
    if user_profile:
        prompt_parts.append("### User Long-Term Memory Profile:")
        prompt_parts.append(f"- Profile Summary: {user_profile.get('profile_summary', '')}")
        prompt_parts.append(f"- Key Interests: {', '.join(user_profile.get('key_topics', []))}\n")

    # 2. Retrieved Knowledge Chunks (RAG)
    if retrieved_chunks:
        prompt_parts.append("### Retrieved Enterprise Knowledge (Indexed via Apache Spark):")
        for i, chunk in enumerate(retrieved_chunks, 1):
            prompt_parts.append(
                f"[Source {i}] Document ID: {chunk['doc_id']} | Title: {chunk['doc_title']} | URI: {chunk['source_uri']}\n"
                f"Content:\n{chunk['content']}\n"
            )
        prompt_parts.append("----------------------------------------\n")

    # 3. Recent Conversation History
    if conversation_history:
        prompt_parts.append("### Recent Conversation Context:")
        for turn in conversation_history[-6:]:
            role_label = "User" if turn["role"] == "user" else "Assistant"
            prompt_parts.append(f"{role_label}: {turn['content']}")
        prompt_parts.append("\n----------------------------------------\n")

    # 4. Current User Query
    prompt_parts.append(f"User Question: {user_query}")
    prompt_parts.append("Assistant Response (Grounded in context above):")

    return "\n".join(prompt_parts)

class ChatOrchestrator:
    """
    Coordinates the full RAG & Multi-Tier Memory pipeline with Multi-Provider Auto-Failover.
    """

    def process_chat_stream(
        self,
        user_query: str,
        session_id: str = "default_session",
        user_id: str = "user_default"
    ) -> Iterator[Dict[str, Any]]:
        """
        Executes query routing, retrieval, streaming generation, and state persistence.
        Yields events: {"event": "citations"|"token"|"done", "data": ...}
        """
        # 1. Fetch Working Memory Context
        history = memory_manager.get_context_window(session_id)
        user_profile = get_user_profile(user_id)

        # 2. Route Query Intent
        intent, model_name = route_query_intent(user_query)
        logger.info(f"Routed query '{user_query[:40]}...' to Intent: {intent}, Model: {model_name}")

        # 3. Retrieve Knowledge Chunks (if RAG required)
        retrieved_chunks = []
        if intent in ("RAG_QUERY", "DEEP_REASONING"):
            retrieved_chunks = retrieve_hybrid_context(user_query, top_k=4)

        # Yield citations event early to frontend
        citations_data = [
            {
                "doc_id": c["doc_id"],
                "doc_title": c["doc_title"],
                "source_uri": c["source_uri"],
                "score": round(float(c.get("score", c.get("rrf_score", 0.0))), 3),
                "snippet": c["content"][:180] + "..."
            }
            for c in retrieved_chunks
        ]
        yield {"event": "metadata", "data": {"intent": intent, "model": model_name, "citations": citations_data}}

        # 4. Assemble Grounded Prompt
        prompt = build_grounded_prompt(
            user_query=user_query,
            conversation_history=history,
            retrieved_chunks=retrieved_chunks,
            user_profile=user_profile
        )

        # 5. Stream Multi-Provider Failover Generation (Gemini -> Groq -> Local)
        full_response_text = []
        for token in failover_client.stream_generate(
            prompt=prompt,
            system_instruction=SYSTEM_PROMPT,
            model_name=model_name,
            context_chunks=retrieved_chunks
        ):
            full_response_text.append(token)
            yield {"event": "token", "data": token}

        complete_response = "".join(full_response_text)

        # 6. Update Memory State (User Turn + Assistant Turn)
        memory_manager.add_turn(
            session_id=session_id,
            user_id=user_id,
            role="user",
            content=user_query
        )
        memory_manager.add_turn(
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            content=complete_response,
            citations=citations_data,
            model_used=model_name
        )

        yield {"event": "done", "data": {"status": "success"}}

orchestrator = ChatOrchestrator()
