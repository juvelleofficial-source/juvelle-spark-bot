import os
from pydantic import BaseModel
from typing import Optional

def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip()
        except Exception:
            pass

_load_env()

class Settings(BaseModel):
    # Application Config
    APP_NAME: str = "Gemini-Spark-Juvelle-Bot"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = True
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")

    # Pure Gemini Spark Architecture (Zero API Keys)
    SPARK_MCP_ENABLED: bool = True
    GEMINI_FLASH_MODEL: str = "gemini-flash-lite-latest"
    GEMINI_PRO_MODEL: str = "gemini-3.6-flash"
    
    # Qdrant Cloud Config (Permanent Free 1GB Cluster)
    QDRANT_URL: Optional[str] = os.getenv("QDRANT_URL")
    QDRANT_API_KEY: Optional[str] = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION_NAME: str = os.getenv("QDRANT_COLLECTION_NAME", "juvelle_knowledge")
    
    # Vector Search Config
    VECTOR_SEARCH_INDEX_ID: str = os.getenv("VECTOR_SEARCH_INDEX_ID", "spark_rag_index_v1")
    EMBEDDING_DIMENSIONS: int = 768

    # Local Memory Config (100% Free)
    MEMORY_WINDOW_SIZE: int = 10
    MEMORY_TTL_SECONDS: int = 86400

    # Spark Config
    SPARK_APP_NAME: str = "GeminiSparkIngestionPipeline"
    SPARK_MASTER: str = os.getenv("SPARK_MASTER", "local[*]")
    SPARK_EMBEDDING_BATCH_SIZE: int = 64
    CHUNK_SIZE_TOKENS: int = 512
    CHUNK_OVERLAP_TOKENS: int = 50

settings = Settings()
