#!/usr/bin/env python3
"""
Juvelle RAG Tool: rag_manager.py
================================
Master Interactive Terminal Dashboard for managing, updating, querying,
and synchronizing the Juvelle RAG Vector Store in real-time.

Usage:
    python rag_tools/rag_manager.py
"""

import os
import sys

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from rag_tools.quick_sync import quick_sync
from rag_tools.add_fact import add_fact
from rag_tools.batch_import import batch_import_folder
from rag_tools.query_tester import test_retrieval_query
from rag_tools.manage_collection import get_collection_stats, list_collection_points, clear_collection
from rag_tools.doc_editor import view_docx_content, rebuild_default_docx

def print_banner():
    print("""
===============================================================
       💎 JUVELLE RAG MANAGEMENT & QUICK UPDATE SUITE 💎       
===============================================================
  1. ⚡ Quick Sync Master KB (data/Juvelle_Knowledge_Base.docx)
  2. ➕ Add Single Fact / Offer / FAQ on the fly
  3. 📁 Bulk Import Folder of Documents (.docx, .md, .txt, .json)
  4. 🔍 Test Live Semantic & Hybrid Retrieval Query
  5. 📊 View Qdrant Cloud Collection Status & Stats
  6. 📋 List Stored Vector Knowledge Points
  7. 📖 Inspect Word (.docx) Document Content
  8. 🔄 Rebuild Default Master Document & Auto-Sync
  9. 🧹 Purge & Reset Qdrant Collection
  0. 🚪 Exit
===============================================================
""")

def run_menu():
    while True:
        print_banner()
        try:
            choice = input("Select an option (0-9): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting RAG Manager.")
            break

        if choice == "1":
            recreate_opt = input("Recreate collection from scratch? (y/N): ").strip().lower() == "y"
            quick_sync(recreate=recreate_opt)
            input("\nPress Enter to continue...")

        elif choice == "2":
            title = input("Enter Title / Category (e.g. 'Festival Offer'): ").strip()
            content = input("Enter Fact / Rule Content: ").strip()
            sync_doc = input("Also append to data/Juvelle_Knowledge_Base.docx? (y/N): ").strip().lower() == "y"
            if title and content:
                add_fact(title=title, content=content, sync_docx=sync_doc)
            else:
                print("⚠️ Title and content cannot be empty.")
            input("\nPress Enter to continue...")

        elif choice == "3":
            folder = input("Enter directory path (e.g. './data'): ").strip() or "./data"
            pattern = input("File filter pattern (default: *.*): ").strip() or "*.*"
            batch_import_folder(folder_path=folder, pattern=pattern)
            input("\nPress Enter to continue...")

        elif choice == "4":
            query = input("Enter test search query: ").strip()
            if query:
                test_retrieval_query(query=query)
            else:
                print("⚠️ Query cannot be empty.")
            input("\nPress Enter to continue...")

        elif choice == "5":
            get_collection_stats()
            input("\nPress Enter to continue...")

        elif choice == "6":
            list_collection_points()
            input("\nPress Enter to continue...")

        elif choice == "7":
            view_docx_content()
            input("\nPress Enter to continue...")

        elif choice == "8":
            rebuild_default_docx()
            quick_sync()
            input("\nPress Enter to continue...")

        elif choice == "9":
            confirm = input("⚠️ Are you sure you want to PURGE all knowledge points in Qdrant Cloud? (y/N): ")
            if confirm.lower() == "y":
                clear_collection()
            else:
                print("Purge aborted.")
            input("\nPress Enter to continue...")

        elif choice == "0":
            print("\nExiting Juvelle RAG Manager. Goodbye! ✨\n")
            break
        else:
            print("Invalid option. Please choose 0 through 9.")

def main():
    run_menu()

if __name__ == "__main__":
    main()
