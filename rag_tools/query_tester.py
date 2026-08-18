#!/usr/bin/env python3
"""
Juvelle RAG Tool: query_tester.py
================================
Interactive real-time semantic & hybrid retrieval tester.
Inspect what knowledge chunks Qdrant Cloud and Local Hybrid RRF return
for any customer prompt, along with similarity scores, ranking, and latency.

Usage:
    python rag_tools/query_tester.py "do you deliver to kochi?"
    python rag_tools/query_tester.py "how much for churidar tops?" --top-k 5
    python rag_tools/query_tester.py "cash on delivery undo?" --json
"""

import os
import sys
import time
import json
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

from retrieval.vector_retriever import retrieve_hybrid_context, search_qdrant_cloud, bm25_lexical_search
from ingestion.batch_embedder import call_vertex_batch_embeddings
from config.settings import settings

logger = logging.getLogger("RAGQueryTester")

def test_retrieval_query(
    query: str,
    top_k: int = 4,
    dense_weight: float = 0.7,
    output_json: bool = False,
    verbose: bool = True
) -> List[Dict[str, Any]]:
    """
    Executes a test retrieval query and measures real-time RAG performance.
    
    Args:
        query: Customer query string to search.
        top_k: Number of top chunks to return.
        dense_weight: Dense vector weighting for Reciprocal Rank Fusion (0.0 to 1.0).
        output_json: If True, prints output as JSON.
        verbose: If True, prints rich visual breakdown.
        
    Returns:
        List of retrieved chunk dictionaries.
    """
    start_time = time.time()
    
    results = retrieve_hybrid_context(
        query=query,
        top_k=top_k,
        dense_weight=dense_weight
    )
    
    elapsed_ms = (time.time() - start_time) * 1000

    if output_json:
        payload = {
            "query": query,
            "latency_ms": round(elapsed_ms, 2),
            "results_count": len(results),
            "chunks": results
        }
        print(json.dumps(payload, indent=2))
        return results

    if verbose:
        print("\n" + "=" * 70)
        print("🔍 JUVELLE RAG: SEMANTIC RETRIEVAL TESTER")
        print("=" * 70)
        print(f"💬 Query:          \"{query}\"")
        print(f"⚙️  Top K:          {top_k}")
        print(f"⚖️  Dense Weight:   {dense_weight} (Dense: {dense_weight*100:.0f}% / Sparse: {(1-dense_weight)*100:.0f}%)")
        print(f"⏱️  Retrieval Time: {elapsed_ms:.2f} ms")
        print("=" * 70)

        if not results:
            print("⚠️ No matching chunks found. Make sure knowledge has been synced via 'quick_sync.py'.")
        else:
            for rank, r in enumerate(results, 1):
                score_display = f"RRF: {r.get('rrf_score', 0):.4f}" if 'rrf_score' in r else f"Score: {r.get('score', 0):.4f}"
                print(f"\n[Rank #{rank}] {score_display} | 📄 {r.get('doc_title', 'Unknown')} ({r.get('chunk_id')})")
                print(f"📍 Source: {r.get('source_uri', 'N/A')}")
                print(f"📝 Content:")
                print(f"   {r.get('content', '')}")
                print("-" * 70)

            print("\n💡 SIMULATED RAG CONTEXT BLOCK INJECTED INTO PROMPT:")
            print("-------------------------------------------------------")
            context_block = "\n---\n".join(r["content"] for r in results)
            print(context_block)
            print("-------------------------------------------------------\n")

    return results

def main():
    parser = argparse.ArgumentParser(description="Test and debug Juvelle RAG retrieval queries.")
    parser.add_argument("query", type=str, help="Search query string.")
    parser.add_argument("--top-k", type=int, default=4, help="Number of chunks to retrieve (default: 4).")
    parser.add_argument("--dense-weight", type=float, default=0.7, help="Dense vector weight 0.0-1.0 (default: 0.7).")
    parser.add_argument("--json", action="store_true", help="Output results formatted as JSON.")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose formatting.")
    args = parser.parse_args()

    test_retrieval_query(
        query=args.query,
        top_k=args.top_k,
        dense_weight=args.dense_weight,
        output_json=args.json,
        verbose=not args.quiet
    )

if __name__ == "__main__":
    main()
