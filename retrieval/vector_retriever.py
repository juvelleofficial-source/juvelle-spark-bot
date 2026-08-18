import logging
import re
from typing import List, Dict, Any, Optional
from ingestion.vector_indexer import search_local_vector_cache, get_qdrant_client, _LOCAL_VECTOR_STORE
from ingestion.batch_embedder import call_vertex_batch_embeddings, generate_local_fallback_embedding
from config.settings import settings

logger = logging.getLogger(__name__)

def search_qdrant_cloud(
    query_vector: List[float],
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Performs cosine semantic search against Qdrant Cloud cluster.
    """
    client = get_qdrant_client()
    if not client:
        return []

    try:
        results = client.query_points(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            query=query_vector,
            limit=top_k
        )
        
        chunks = []
        for point in results.points:
            payload = point.payload or {}
            chunks.append({
                "chunk_id": payload.get("chunk_id", str(point.id)),
                "doc_id": payload.get("doc_id", "juvelle_doc"),
                "doc_title": payload.get("doc_title", "Juvelle Knowledge"),
                "source_uri": payload.get("source_uri", "Juvelle_Knowledge_Base.docx"),
                "content": payload.get("content", ""),
                "score": point.score
            })
        return chunks
    except Exception as e:
        logger.warning(f"Qdrant Cloud search error ({e}), falling back to local vector store.")
        return []

def bm25_lexical_search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    100% Free lexical keyword search using term frequency across local indexed chunks.
    """
    if not _LOCAL_VECTOR_STORE:
        return []

    keywords = set(re.findall(r'\w+', query.lower()))
    if not keywords:
        return []

    scored_chunks = []
    for item in _LOCAL_VECTOR_STORE:
        content_words = re.findall(r'\w+', item["content"].lower())
        if not content_words:
            continue
        
        matches = sum(1 for w in content_words if w in keywords)
        score = matches / (len(content_words) + 1.0)
        
        if score > 0:
            scored_chunks.append({
                "chunk_id": item["chunk_id"],
                "doc_id": item["doc_id"],
                "doc_title": item["doc_title"],
                "source_uri": item["source_uri"],
                "content": item["content"],
                "score": score
            })

    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    return scored_chunks[:top_k]

def retrieve_hybrid_context(
    query: str,
    top_k: int = 4,
    dense_weight: float = 0.7
) -> List[Dict[str, Any]]:
    """
    Combines dense semantic vector retrieval (Qdrant Cloud with local fallback)
    with sparse lexical keyword matching using Reciprocal Rank Fusion (RRF).
    """
    # 1. Embed query vector
    query_vectors = call_vertex_batch_embeddings([query])
    q_vec = query_vectors[0] if query_vectors else generate_local_fallback_embedding(query, settings.EMBEDDING_DIMENSIONS)

    # 2. Dense Vector Retrieval (Qdrant Cloud -> Local Fallback)
    dense_results = search_qdrant_cloud(query_vector=q_vec, top_k=top_k * 2)
    if not dense_results:
        dense_results = search_local_vector_cache(query_vector=q_vec, top_k=top_k * 2)

    # 3. Lexical Keyword Retrieval
    lexical_results = bm25_lexical_search(query=query, top_k=top_k * 2)

    # 4. Reciprocal Rank Fusion (RRF)
    rrf_scores: Dict[str, float] = {}
    chunk_map: Dict[str, Dict[str, Any]] = {}
    k_constant = 60

    for rank, item in enumerate(dense_results):
        c_id = item["chunk_id"]
        chunk_map[c_id] = item
        rrf_scores[c_id] = rrf_scores.get(c_id, 0.0) + (dense_weight * (1.0 / (k_constant + rank + 1)))

    for rank, item in enumerate(lexical_results):
        c_id = item["chunk_id"]
        chunk_map[c_id] = item
        rrf_scores[c_id] = rrf_scores.get(c_id, 0.0) + ((1.0 - dense_weight) * (1.0 / (k_constant + rank + 1)))

    # Sort candidates by combined RRF score
    sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
    
    final_chunks = []
    for cid in sorted_chunk_ids[:top_k]:
        item = chunk_map[cid]
        item["rrf_score"] = rrf_scores[cid]
        final_chunks.append(item)

    logger.info(f"Hybrid retrieval returned {len(final_chunks)} chunks for query: '{query}'")
    return final_chunks
