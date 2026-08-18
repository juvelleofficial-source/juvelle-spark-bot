import json
import math
import logging
import uuid
from typing import List, Dict, Any, Optional
from config.settings import settings

logger = logging.getLogger(__name__)

# Local in-memory vector store for standalone execution / dev fallback (100% Free)
_LOCAL_VECTOR_STORE: List[Dict[str, Any]] = []

def get_qdrant_client():
    """Initializes and returns an authenticated Qdrant Cloud client if credentials exist."""
    if settings.QDRANT_URL and settings.QDRANT_API_KEY:
        try:
            from qdrant_client import QdrantClient
            return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=10)
        except Exception as e:
            logger.warning(f"Failed to initialize Qdrant client: {e}")
    return None

def export_for_vertex_vector_search(df_embedded: Any, output_gcs_uri: str) -> None:
    """Exports the Spark embedded chunks into Vertex AI Vector Search JSONL format."""
    pass

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """
    Pure Python cosine similarity calculation without external C++ or NumPy dependencies.
    """
    if len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)

def sync_to_qdrant_cloud(records: List[Dict[str, Any]]) -> bool:
    """
    Syncs and upserts vector embeddings into Qdrant Cloud collection.
    """
    client = get_qdrant_client()
    if not client:
        return False

    try:
        from qdrant_client.models import Distance, VectorParams, PointStruct

        collection_name = settings.QDRANT_COLLECTION_NAME
        collections_resp = client.get_collections()
        existing = [c.name for c in collections_resp.collections]

        dim = len(records[0]["embedding"]) if records else settings.EMBEDDING_DIMENSIONS
        if collection_name not in existing:
            logger.info(f"Creating Qdrant collection '{collection_name}' with dim {dim}...")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
            )

        points = []
        for idx, r in enumerate(records):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{r['chunk_id']}_{idx}"))
            points.append(
                PointStruct(
                    id=point_id,
                    vector=[float(x) for x in r["embedding"]],
                    payload={
                        "chunk_id": r["chunk_id"],
                        "doc_id": r["doc_id"],
                        "doc_title": r["doc_title"],
                        "source_uri": r["source_uri"],
                        "chunk_index": r["chunk_index"],
                        "content": r["content"],
                        "token_count": r.get("token_count", 0)
                    }
                )
            )

        if points:
            client.upsert(collection_name=collection_name, points=points)
            logger.info(f"Successfully upserted {len(points)} vector points to Qdrant Cloud collection '{collection_name}'.")
        return True
    except Exception as e:
        logger.error(f"Error syncing to Qdrant Cloud: {e}")
        return False

def sync_to_local_vector_cache(df_embedded: Any) -> int:
    """
    Collects embedded records to populate the local memory store and syncs to Qdrant Cloud.
    """
    global _LOCAL_VECTOR_STORE
    records = df_embedded.collect()
    _LOCAL_VECTOR_STORE = []
    
    dict_records = []
    for r in records:
        row_dict = r if isinstance(r, dict) else r.__dict__
        item = {
            "chunk_id": row_dict["chunk_id"],
            "doc_id": row_dict["doc_id"],
            "doc_title": row_dict["doc_title"],
            "source_uri": row_dict["source_uri"],
            "chunk_index": row_dict["chunk_index"],
            "content": row_dict["content"],
            "token_count": row_dict["token_count"],
            "embedding": [float(x) for x in row_dict["embedding"]]
        }
        _LOCAL_VECTOR_STORE.append(item)
        dict_records.append(item)
    
    logger.info(f"Synced {len(_LOCAL_VECTOR_STORE)} chunks to local vector cache.")
    
    # Also sync to Qdrant Cloud
    sync_to_qdrant_cloud(dict_records)
    
    return len(_LOCAL_VECTOR_STORE)

def search_local_vector_cache(
    query_vector: List[float],
    top_k: int = 5,
    filter_doc_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Performs pure Python cosine similarity search across the local vector cache.
    """
    global _LOCAL_VECTOR_STORE
    if not _LOCAL_VECTOR_STORE:
        return []

    results = []
    for item in _LOCAL_VECTOR_STORE:
        if filter_doc_id and item["doc_id"] != filter_doc_id:
            continue
        
        sim = cosine_similarity(query_vector, item["embedding"])
        results.append({
            "chunk_id": item["chunk_id"],
            "doc_id": item["doc_id"],
            "doc_title": item["doc_title"],
            "source_uri": item["source_uri"],
            "content": item["content"],
            "score": sim
        })

    # Sort descending by similarity score
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
