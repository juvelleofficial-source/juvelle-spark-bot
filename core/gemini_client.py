import os
import time
import logging
from typing import Iterator, List, Dict, Any, Optional
from config.settings import settings

logger = logging.getLogger(__name__)

def stream_mock_response(prompt: str, context_chunks: List[Dict[str, Any]]) -> Iterator[str]:
    """
    Offline mock response generator for Spark enterprise pipelines.
    """
    time.sleep(0.05)
    yield "### Spark & Gemini Enterprise Response\n\n"
    yield "Based on the enterprise knowledge processed by our **Apache Spark Ingestion Pipeline** and indexed in our vector store:\n\n"
    
    if context_chunks:
        yield f"- **Retrieved Knowledge Chunks**: Found **{len(context_chunks)}** highly relevant document segments.\n"
        for i, chk in enumerate(context_chunks, 1):
            yield f"- **Source {i}** (`{chk['doc_title']}`): {chk['content'][:140]}...\n"
        yield "\n"
    
    yield "#### Key Architectural Takeaways:\n\n"
    yield "1. **Apache Spark Role**: Runs distributed batch ETL, chunking, and embedding generation across documents.\n"
    yield "2. **Model Context Protocol**: Autonomous reasoning is performed directly by Gemini Spark via MCP.\n"

class GeminiClient:
    """
    Zero-API-key client for Spark & MCP workflows.
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", None)
        self._client = None

    def stream_generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
        context_chunks: Optional[List[Dict[str, Any]]] = None
    ) -> Iterator[str]:
        chunks = context_chunks or []
        for token in stream_mock_response(prompt, chunks):
            yield token

gemini_client = GeminiClient()
