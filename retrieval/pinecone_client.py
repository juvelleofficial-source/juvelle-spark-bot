import os
import json
import logging
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional
from ingestion.batch_embedder import generate_local_fallback_embedding, call_vertex_batch_embeddings

logger = logging.getLogger("PineconeClient")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "pcsk_cD2Zr_SLxybS4YqvpwVKmGBGrUs2PwWw2Cx9utRSugHepAUqy7JxLSBtXjjk6Wu7BSxjn")
PINECONE_HOST = os.getenv("PINECONE_HOST", "https://gemini-memory-4gbye74.svc.aped-4627-b74a.pinecone.io")
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "gemini-memory")
DIMENSION = 768

JUVELLE_KNOWLEDGE_DOCS = [
    {
        "id": "juvelle_brand_core",
        "text": "Juvelle is a women's clothing brand selling premium quality Churidar tops for daily wear and office wear. USP: Premium quality fabric at the most affordable price.",
        "category": "brand"
    },
    {
        "id": "juvelle_delivery_shipping",
        "text": "Juvelle delivers exclusively to KERALA ONLY. We do NOT deliver outside Kerala (Bangalore, Mumbai, Dubai etc). All packages are dispatched next day via Delhivery courier service.",
        "category": "shipping"
    },
    {
        "id": "juvelle_ordering_process",
        "text": "Ordering process: Customers must send a screenshot of the top they like along with their size. We confirm availability and share payment details. Once paid, orders ship next day via Delhivery. Juvelle does NOT have a website yet.",
        "category": "ordering"
    },
    {
        "id": "juvelle_payment_policy",
        "text": "Payment methods: We accept online payments (UPI, GPay, PhonePe, Paytm) and Bank Transfers. We do NOT offer Cash on Delivery (COD). Reason: Currently we accept online payments to ensure faster dispatch.",
        "category": "payment"
    },
    {
        "id": "juvelle_product_catalog",
        "text": "Products: Exclusively Churidar tops made with breathable cotton and premium rayon blends suitable for daily wear, office wear, and college wear. Standard price range is ₹399 - ₹899.",
        "category": "products"
    }
]

def pinecone_request(endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{PINECONE_HOST.rstrip('/')}{endpoint}"
    headers = {
        "Api-Key": PINECONE_API_KEY,
        "Content-Type": "application/json"
    }
    
    req_body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=req_body, headers=headers, method="POST" if data is not None else "GET")
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        logger.error(f"Pinecone HTTP Error {e.code} on {endpoint}: {err_msg}")
        raise RuntimeError(f"Pinecone API Error ({e.code}): {err_msg}")
    except Exception as e:
        logger.error(f"Pinecone Request Error on {endpoint}: {e}")
        raise e

def seed_juvelle_knowledge_to_pinecone() -> int:
    """
    Seeds Juvelle brand knowledge into Pinecone vector index gemini-memory.
    """
    vectors = []
    for doc in JUVELLE_KNOWLEDGE_DOCS:
        # Generate 768-dim embedding
        embeddings = call_vertex_batch_embeddings([doc["text"]])
        if embeddings and len(embeddings[0]) == DIMENSION:
            vec = embeddings[0]
        else:
            vec = generate_local_fallback_embedding(doc["text"], dimension=DIMENSION)
        
        vectors.append({
            "id": doc["id"],
            "values": vec,
            "metadata": {
                "text": doc["text"],
                "category": doc["category"],
                "source": "juvelle_knowledge_base"
            }
        })
    
    payload = {"vectors": vectors}
    res = pinecone_request("/vectors/upsert", data=payload)
    upserted_count = res.get("upsertedCount", len(vectors))
    logger.info(f"Successfully upserted {upserted_count} vectors into Pinecone '{INDEX_NAME}'")
    return upserted_count

def query_pinecone_memory(query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Queries the Pinecone gemini-memory index with dense vector search.
    """
    embeddings = call_vertex_batch_embeddings([query_text])
    if embeddings and len(embeddings[0]) == DIMENSION:
        query_vec = embeddings[0]
    else:
        query_vec = generate_local_fallback_embedding(query_text, dimension=DIMENSION)
    
    payload = {
        "vector": query_vec,
        "topK": top_k,
        "includeMetadata": True
    }
    
    try:
        res = pinecone_request("/query", data=payload)
        matches = res.get("matches", [])
        results = []
        for m in matches:
            results.append({
                "id": m.get("id"),
                "score": m.get("score", 0.0),
                "text": m.get("metadata", {}).get("text", ""),
                "category": m.get("metadata", {}).get("category", "general")
            })
        return results
    except Exception as e:
        logger.warning(f"Pinecone query failed, using local fallback: {e}")
        # Fallback to in-memory docs matching
        keywords = set(query_text.lower().split())
        matched = []
        for doc in JUVELLE_KNOWLEDGE_DOCS:
            text_words = set(doc["text"].lower().split())
            overlap = len(keywords.intersection(text_words))
            matched.append({"id": doc["id"], "score": overlap / (len(keywords) + 1), "text": doc["text"], "category": doc["category"]})
        matched.sort(key=lambda x: x["score"], reverse=True)
        return matched[:top_k]
