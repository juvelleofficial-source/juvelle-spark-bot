#!/usr/bin/env python3
"""
Juvelle RAG Tool: quick_sync.py
===============================
Ultra-fast direct Python ingestion tool (<1-2s) that parses knowledge documents,
generates dense vector embeddings, and immediately upserts to Qdrant Cloud
and the local in-memory hybrid vector cache.

Usage:
    python rag_tools/quick_sync.py
    python rag_tools/quick_sync.py --file data/Juvelle_Knowledge_Base.docx
    python rag_tools/quick_sync.py --recreate
"""

import os
import sys
import time
import argparse
import logging
from typing import List, Dict, Any

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import settings
from ingestion.document_processor import load_documents_from_docx, chunk_text_content
from ingestion.batch_embedder import call_vertex_batch_embeddings, generate_local_fallback_embedding
from ingestion.vector_indexer import get_qdrant_client, sync_to_qdrant_cloud, _LOCAL_VECTOR_STORE

logger = logging.getLogger("RAGQuickSync")

def quick_sync(file_path: str = None, recreate: bool = False, verbose: bool = True) -> int:
    """
    Executes an ultra-fast synchronization of the knowledge base into Qdrant Cloud.
    
    Args:
        file_path: Path to .docx, .md, or .txt file. Defaults to data/Juvelle_Knowledge_Base.docx.
        recreate: If True, purges and recreates the Qdrant collection before upserting.
        verbose: If True, prints formatted console logs.
        
    Returns:
        int: Number of semantic chunks successfully indexed.
    """
    start_time = time.time()
    
    if file_path is None:
        file_path = os.path.join(PROJECT_ROOT, "data", "Juvelle_Knowledge_Base.docx")

    if verbose:
        print("\n" + "=" * 60)
        print("⚡ JUVELLE RAG: ULTRA-FAST VECTOR SYNC")
        print("=" * 60)
        print(f"📁 Target Document: {file_path}")
        print(f"🌐 Qdrant URL:     {settings.QDRANT_URL or 'Local In-Memory Fallback'}")
        print(f"📦 Collection:     {settings.QDRANT_COLLECTION_NAME}")
        print("=" * 60)

    # 1. Load Raw Document Sections
    raw_docs: List[Dict[str, str]] = []
    if os.path.exists(file_path):
        if file_path.endswith(".docx"):
            raw_docs = load_documents_from_docx(file_path)
        else:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            raw_docs = [{
                "doc_id": f"DOC_{os.path.basename(file_path)}",
                "doc_title": os.path.basename(file_path),
                "source_uri": f"file://{os.path.basename(file_path)}",
                "raw_text": content
            }]
    else:
        if verbose:
            print(f"⚠️ Warning: File '{file_path}' not found! Using built-in fallback catalog chunks.")
        raw_docs = [
            {
                "doc_id": "JUV_001",
                "doc_title": "Juvelle Brand Identity & Apparel Catalog",
                "source_uri": "juvelle://catalog/products_and_pricing.md",
                "raw_text": (
                    "Juvelle is an exclusive women's clothing boutique based in Kerala. "
                    "USP: Premium quality fabric at the most affordable price. "
                    "Products: Exclusively Churidar tops made with breathable cotton and premium rayon blends "
                    "suitable for daily wear, office wear, and college wear. "
                    "Standard price range is ₹399 - ₹899. "
                    "Juvelle does NOT sell kids wear, men wear, western clothing, sarees, frocks, jeans, or t-shirts."
                )
            },
            {
                "doc_id": "JUV_002",
                "doc_title": "Juvelle Shipping, Logistics & Delivery Coverage",
                "source_uri": "juvelle://logistics/delivery_policy.md",
                "raw_text": (
                    "Delivery Location: KERALA ONLY. Juvelle currently delivers exclusively to addresses within Kerala. "
                    "Orders to other states or abroad (Tamil Nadu, Bangalore, Mumbai, Dubai, etc.) are politely declined. "
                    "Courier Partner: Delhivery courier service. "
                    "Dispatch Timeline: Next working day after payment confirmation. "
                    "Delivery Time: Usually 2-3 business days anywhere in Kerala."
                )
            },
            {
                "doc_id": "JUV_003",
                "doc_title": "Juvelle Ordering Process & Payment Methods",
                "source_uri": "juvelle://sales/ordering_and_payment.md",
                "raw_text": (
                    "Website: Juvelle does NOT have an official website yet. "
                    "How to Order: Customers place orders directly in chat by sending a screenshot of the desired Churidar top "
                    "along with their required size (S, M, L, XL, XXL). "
                    "Payment Method: Online payment only (UPI, Google Pay, PhonePe, Paytm, direct Bank Transfer). "
                    "Cash on Delivery (COD) is NOT available to ensure rapid next-day dispatch."
                )
            },
            {
                "doc_id": "JUV_004",
                "doc_title": "Juvelle Quality, Fabric Care & Customer Support",
                "source_uri": "juvelle://support/fabric_and_contact.md",
                "raw_text": (
                    "Fabric Quality: 100% breathable pure cotton and premium soft rayon blends tested for daily comfort. "
                    "Customer Support: Support is handled right here via Instagram Direct Message and WhatsApp chat. "
                    "Return & Exchanges: Damaged items are replaced upon providing an opening video; size assistance is provided prior to dispatch."
                )
            }
        ]

    # 2. Semantic Token Chunking
    all_chunks: List[Dict[str, Any]] = []
    for doc in raw_docs:
        chunks = chunk_text_content(
            text=doc.get("raw_text", ""),
            doc_id=doc.get("doc_id", "DOC"),
            doc_title=doc.get("doc_title", "Juvelle Document"),
            source_uri=doc.get("source_uri", "file://local"),
            chunk_size=settings.CHUNK_SIZE_TOKENS,
            chunk_overlap=settings.CHUNK_OVERLAP_TOKENS
        )
        all_chunks.extend(chunks)

    if verbose:
        print(f"✂️  Extracted {len(raw_docs)} sections -> {len(all_chunks)} semantic chunks.")

    # 3. Fast Batch Embedding Generation
    texts = [c["content"] for c in all_chunks]
    embeddings = call_vertex_batch_embeddings(texts)
    
    records = []
    for chunk, emb in zip(all_chunks, embeddings):
        record = dict(chunk)
        record["embedding"] = emb
        records.append(record)

    # 4. Collection Recreation if requested
    client = get_qdrant_client()
    if recreate and client:
        try:
            from qdrant_client.models import Distance, VectorParams
            if verbose:
                print(f"🗑️  Recreating Qdrant collection '{settings.QDRANT_COLLECTION_NAME}'...")
            client.delete_collection(collection_name=settings.QDRANT_COLLECTION_NAME)
            client.create_collection(
                collection_name=settings.QDRANT_COLLECTION_NAME,
                vectors_config=VectorParams(size=settings.EMBEDDING_DIMENSIONS, distance=Distance.COSINE)
            )
        except Exception as e:
            if verbose:
                print(f"⚠️ Collection recreate note: {e}")

    # 5. Upsert to Qdrant Cloud
    qdrant_synced = sync_to_qdrant_cloud(records)
    
    # 6. Update local vector store in-memory
    _LOCAL_VECTOR_STORE.clear()
    _LOCAL_VECTOR_STORE.extend(records)

    elapsed_ms = (time.time() - start_time) * 1000

    if verbose:
        print(f"☁️  Qdrant Cloud Upsert: {'✅ Success' if qdrant_synced else '⚠️ Offline / Skipped'}")
        print(f"🧠 Local Cache Store:  ✅ {len(_LOCAL_VECTOR_STORE)} chunks active")
        print(f"⏱️  Execution Time:    {elapsed_ms:.1f} ms")
        print("=" * 60 + "\n")

    return len(records)

def main():
    parser = argparse.ArgumentParser(description="Quick-sync documents into Juvelle RAG Vector Store.")
    parser.add_argument("--file", type=str, default=None, help="Path to .docx or text document to index.")
    parser.add_argument("--recreate", action="store_true", help="Recreate Qdrant collection from scratch.")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output.")
    args = parser.parse_args()

    quick_sync(file_path=args.file, recreate=args.recreate, verbose=not args.quiet)

if __name__ == "__main__":
    main()
