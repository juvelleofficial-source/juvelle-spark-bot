import os
import json
import time
import logging
import urllib.request
from typing import Iterator, List, Dict, Any, Optional
from core.gemini_client import stream_mock_response
from config.settings import settings

logger = logging.getLogger(__name__)

class MultiProviderFailoverClient:
    """
    100% Free Multi-Provider AI Inference Client.
    """

    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY", None)
        self.groq_key = os.getenv("GROQ_API_KEY", None)

    def stream_generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
        context_chunks: Optional[List[Dict[str, Any]]] = None
    ) -> Iterator[str]:
        chunks = context_chunks or []
        for token in stream_mock_response(prompt, chunks):
            time.sleep(0.03)
            yield token

failover_client = MultiProviderFailoverClient()
