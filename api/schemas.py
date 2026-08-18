from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ChatRequest(BaseModel):
    query: str = Field(..., description="User prompt or question")
    session_id: str = Field(default="default_session", description="Conversation session ID")
    user_id: str = Field(default="user_default", description="Unique user identifier")

class CitationModel(BaseModel):
    doc_id: str
    doc_title: str
    source_uri: str
    score: float
    snippet: str

class IngestionRequest(BaseModel):
    documents: Optional[List[Dict[str, str]]] = Field(default=None, description="Optional custom document payload")
    export_gcs: bool = Field(default=False, description="Whether to export to GCS format")

class IngestionResponse(BaseModel):
    status: str
    chunks_indexed: int
    message: str

class MemoryInspectResponse(BaseModel):
    session_id: str
    user_id: str
    short_term_turns: List[Dict[str, Any]]
    user_profile: Optional[Dict[str, Any]] = None

class HealthResponse(BaseModel):
    app_name: str
    version: str
    status: str
    indexed_vectors: int
    gemini_api_configured: bool
