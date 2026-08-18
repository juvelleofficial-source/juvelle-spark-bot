#!/usr/bin/env python3
"""
Juvelle RAG Tool: batch_import.py
================================
Bulk imports and indexes all documents (.docx, .md, .txt, .json, .csv)
found in a folder directly into Qdrant Cloud.

Usage:
    python rag_tools/batch_import.py --dir ./data
    python rag_tools/batch_import.py --dir ./docs --pattern "*.md"
"""

import os
import sys
import glob
import time
import json
import csv
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
from ingestion.batch_embedder import call_vertex_batch_embeddings
from ingestion.vector_indexer import sync_to_qdrant_cloud, _LOCAL_VECTOR_STORE

logger = logging.getLogger("RAGBatchImport")

def parse_file(file_path: str) -> List[Dict[str, str]]:
    """Parses a single file into raw document dictionaries."""
    ext = os.path.splitext(file_path)[1].lower()
    base_name = os.path.basename(file_path)
    
    if ext == ".docx":
        return load_documents_from_docx(file_path)
        
    elif ext in [".txt", ".md", ".markdown"]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            return [{
                "doc_id": f"DOC_{base_name}",
                "doc_title": base_name,
                "source_uri": f"file://{base_name}",
                "raw_text": text
            }]
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            return []

    elif ext == ".json":
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            docs = []
            if isinstance(data, list):
                for idx, item in enumerate(data):
                    text = item.get("content") or item.get("text") or json.dumps(item)
                    title = item.get("title") or f"{base_name} #{idx+1}"
                    docs.append({
                        "doc_id": f"{base_name}_{idx}",
                        "doc_title": title,
                        "source_uri": f"json://{base_name}#{idx}",
                        "raw_text": text
                    })
            elif isinstance(data, dict):
                docs.append({
                    "doc_id": f"DOC_{base_name}",
                    "doc_title": data.get("title", base_name),
                    "source_uri": f"json://{base_name}",
                    "raw_text": data.get("content", json.dumps(data, indent=2))
                })
            return docs
        except Exception as e:
            logger.error(f"Error reading JSON {file_path}: {e}")
            return []

    elif ext == ".csv":
        try:
            docs = []
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader):
                    content_str = " | ".join(f"{k}: {v}" for k, v in row.items() if v)
                    title = row.get("title") or row.get("name") or row.get("product") or f"{base_name} Row {idx+1}"
                    docs.append({
                        "doc_id": f"CSV_{base_name}_{idx}",
                        "doc_title": title,
                        "source_uri": f"csv://{base_name}#{idx}",
                        "raw_text": content_str
                    })
            return docs
        except Exception as e:
            logger.error(f"Error reading CSV {file_path}: {e}")
            return []

    return []

def batch_import_folder(folder_path: str, pattern: str = "*.*", verbose: bool = True) -> int:
    """
    Imports all matching files in a folder into Qdrant Cloud.
    
    Args:
        folder_path: Directory path to scan.
        pattern: Glob pattern to filter files (e.g. '*.md').
        verbose: If True, outputs step-by-step progress.
        
    Returns:
        int: Total number of chunks indexed.
    """
    start_time = time.time()
    
    if not os.path.exists(folder_path):
        print(f"❌ Error: Folder '{folder_path}' does not exist.")
        return 0

    if verbose:
        print("\n" + "=" * 60)
        print("📁 JUVELLE RAG: BATCH FOLDER IMPORT")
        print("=" * 60)
        print(f"📂 Folder:        {folder_path}")
        print(f"🔍 Pattern:       {pattern}")
        print("=" * 60)

    # Collect files
    supported_extensions = {".docx", ".md", ".txt", ".json", ".csv"}
    all_files = []
    for root, _, files in os.walk(folder_path):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in supported_extensions:
                all_files.append(os.path.join(root, f))

    if not all_files:
        if verbose:
            print("⚠️ No supported documents (.docx, .md, .txt, .json, .csv) found in directory.")
        return 0

    if verbose:
        print(f"📄 Found {len(all_files)} document(s) to process:")
        for f in all_files:
            print(f"   • {os.path.basename(f)} ({os.path.getsize(f)} bytes)")

    # Parse and chunk
    all_chunks: List[Dict[str, Any]] = []
    for file_path in all_files:
        docs = parse_file(file_path)
        for d in docs:
            chunks = chunk_text_content(
                text=d.get("raw_text", ""),
                doc_id=d.get("doc_id", "DOC"),
                doc_title=d.get("doc_title", "Document"),
                source_uri=d.get("source_uri", f"file://{os.path.basename(file_path)}"),
                chunk_size=settings.CHUNK_SIZE_TOKENS,
                chunk_overlap=settings.CHUNK_OVERLAP_TOKENS
            )
            all_chunks.extend(chunks)

    if not all_chunks:
        if verbose:
            print("⚠️ No valid text content could be extracted from files.")
        return 0

    if verbose:
        print(f"\n✂️  Generated {len(all_chunks)} semantic chunks across all files.")
        print("⚡ Generating batch vector embeddings...")

    # Embed and sync
    texts = [c["content"] for c in all_chunks]
    embeddings = call_vertex_batch_embeddings(texts)

    records = []
    for chunk, emb in zip(all_chunks, embeddings):
        rec = dict(chunk)
        rec["embedding"] = emb
        records.append(rec)

    qdrant_synced = sync_to_qdrant_cloud(records)
    _LOCAL_VECTOR_STORE.extend(records)

    elapsed_ms = (time.time() - start_time) * 1000

    if verbose:
        print(f"☁️  Qdrant Cloud Upsert: {'✅ Success' if qdrant_synced else '⚠️ Offline / Skipped'}")
        print(f"🧠 Local Store Total:   {len(_LOCAL_VECTOR_STORE)} chunks")
        print(f"⏱️  Total Elapsed Time:  {elapsed_ms:.1f} ms")
        print("=" * 60 + "\n")

    return len(records)

def main():
    parser = argparse.ArgumentParser(description="Bulk import knowledge files into Juvelle RAG.")
    parser.add_argument("--dir", type=str, required=True, help="Path to directory containing documents.")
    parser.add_argument("--pattern", type=str, default="*.*", help="File filter pattern (e.g. '*.md').")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output.")
    args = parser.parse_args()

    batch_import_folder(folder_path=args.dir, pattern=args.pattern, verbose=not args.quiet)

if __name__ == "__main__":
    main()
