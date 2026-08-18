#!/usr/bin/env python3
"""
Juvelle RAG Tool: manage_collection.py
======================================
Qdrant Cloud vector collection administration tool.
View collection statistics, inspect point payloads, delete specific records,
export backups, or purge and reset the collection.

Usage:
    python rag_tools/manage_collection.py --status
    python rag_tools/manage_collection.py --list
    python rag_tools/manage_collection.py --delete-id <point_id>
    python rag_tools/manage_collection.py --export backup_rag.json
    python rag_tools/manage_collection.py --clear
"""

import os
import sys
import json
import argparse
import logging
from typing import Dict, Any, List

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
from ingestion.vector_indexer import get_qdrant_client, _LOCAL_VECTOR_STORE

logger = logging.getLogger("RAGManageCollection")

def get_collection_stats(verbose: bool = True) -> Dict[str, Any]:
    """Retrieves metadata and health statistics for the active Qdrant collection."""
    client = get_qdrant_client()
    stats = {
        "connected": False,
        "collection_name": settings.QDRANT_COLLECTION_NAME,
        "qdrant_url": settings.QDRANT_URL,
        "points_count": 0,
        "vectors_count": 0,
        "status": "offline",
        "local_cache_count": len(_LOCAL_VECTOR_STORE)
    }
    
    if not client:
        if verbose:
            print("\n⚠️ Qdrant Cloud client not configured or unreachable.")
            print(f"🧠 Local Memory Cache: {len(_LOCAL_VECTOR_STORE)} chunks active.")
        return stats

    try:
        col_info = client.get_collection(collection_name=settings.QDRANT_COLLECTION_NAME)
        stats["connected"] = True
        stats["points_count"] = getattr(col_info, "points_count", 0) or 0
        stats["vectors_count"] = getattr(col_info, "indexed_vectors_count", stats["points_count"]) or stats["points_count"]
        
        status_val = getattr(col_info, "status", "green")
        stats["status"] = status_val.value if hasattr(status_val, 'value') else str(status_val)
        
        if verbose:
            print("\n" + "=" * 60)
            print("📊 JUVELLE RAG: QDRANT CLOUD COLLECTION STATUS")
            print("=" * 60)
            print(f"📦 Collection Name:   {stats['collection_name']}")
            print(f"🌐 Cluster URL:       {stats['qdrant_url']}")
            print(f"🟢 Cluster Status:     {stats['status']}")
            print(f"🔢 Total Points:      {stats['points_count']}")
            print(f"📐 Indexed Vectors:   {stats['vectors_count']}")
            print(f"🧠 Local Cache Store: {stats['local_cache_count']} active chunks")
            print("=" * 60 + "\n")
            
        return stats
    except Exception as e:
        stats["error"] = str(e)
        if verbose:
            print(f"⚠️ Error fetching collection info: {e}")
        return stats

def list_collection_points(limit: int = 50, verbose: bool = True) -> List[Dict[str, Any]]:
    """Scrolls and lists stored vector points and payloads from Qdrant Cloud."""
    client = get_qdrant_client()
    if not client:
        print("⚠️ Qdrant Cloud is not connected.")
        return []

    try:
        points, _ = client.scroll(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )
        
        if verbose:
            print("\n" + "=" * 70)
            print(f"📋 JUVELLE RAG: STORED KNOWLEDGE POINTS (Showing {len(points)})")
            print("=" * 70)
            for idx, p in enumerate(points, 1):
                payload = p.payload or {}
                print(f"[{idx}] ID: {p.id}")
                print(f"    Title:   {payload.get('doc_title', 'N/A')}")
                print(f"    Chunk:   {payload.get('chunk_id', 'N/A')}")
                print(f"    Source:  {payload.get('source_uri', 'N/A')}")
                content = payload.get('content', '')
                snippet = (content[:90] + '...') if len(content) > 90 else content
                print(f"    Preview: {snippet}")
                print("-" * 70)
            print()
            
        return [{"id": str(p.id), "payload": p.payload} for p in points]
    except Exception as e:
        print(f"❌ Error scrolling points: {e}")
        return []

def delete_point(point_id: str, verbose: bool = True) -> bool:
    """Deletes a specific vector point by ID from Qdrant Cloud."""
    client = get_qdrant_client()
    if not client:
        print("⚠️ Qdrant Cloud is not connected.")
        return False

    try:
        client.delete(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points_selector=[point_id]
        )
        if verbose:
            print(f"✅ Successfully deleted point ID: {point_id}")
        return True
    except Exception as e:
        print(f"❌ Error deleting point {point_id}: {e}")
        return False

def export_collection(output_path: str, verbose: bool = True) -> bool:
    """Exports all points and payloads from Qdrant Cloud to a JSON backup file."""
    client = get_qdrant_client()
    if not client:
        print("⚠️ Qdrant Cloud is not connected.")
        return False

    try:
        points, _ = client.scroll(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            limit=10000,
            with_payload=True,
            with_vectors=True
        )
        
        data = []
        for p in points:
            data.append({
                "id": str(p.id),
                "payload": p.payload,
                "vector": p.vector
            })
            
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        if verbose:
            print(f"💾 Successfully exported {len(data)} points to '{output_path}'.")
        return True
    except Exception as e:
        print(f"❌ Export failed: {e}")
        return False

def clear_collection(verbose: bool = True) -> bool:
    """Purges all points and recreates an empty collection in Qdrant Cloud."""
    client = get_qdrant_client()
    if not client:
        print("⚠️ Qdrant Cloud is not connected.")
        return False

    try:
        from qdrant_client.models import Distance, VectorParams
        client.delete_collection(collection_name=settings.QDRANT_COLLECTION_NAME)
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(size=settings.EMBEDDING_DIMENSIONS, distance=Distance.COSINE)
        )
        _LOCAL_VECTOR_STORE.clear()
        if verbose:
            print(f"🧹 Purged and cleanly recreated collection '{settings.QDRANT_COLLECTION_NAME}'.")
        return True
    except Exception as e:
        print(f"❌ Error clearing collection: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Manage Juvelle Qdrant Cloud vector collection.")
    parser.add_argument("--status", action="store_true", help="Display collection status and point count.")
    parser.add_argument("--list", action="store_true", help="List stored points and payloads.")
    parser.add_argument("--delete-id", type=str, default=None, help="Delete a specific point by its ID.")
    parser.add_argument("--export", type=str, default=None, help="Export collection backup to JSON file.")
    parser.add_argument("--clear", action="store_true", help="Wipe and recreate empty collection.")
    args = parser.parse_args()

    if args.status:
        get_collection_stats()
    elif args.list:
        list_collection_points()
    elif args.delete_id:
        delete_point(args.delete_id)
    elif args.export:
        export_collection(args.export)
    elif args.clear:
        confirm = input("⚠️ Are you sure you want to PURGE all knowledge points in Qdrant Cloud? (y/N): ")
        if confirm.lower() == "y":
            clear_collection()
        else:
            print("Purge aborted.")
    else:
        get_collection_stats()

if __name__ == "__main__":
    main()
