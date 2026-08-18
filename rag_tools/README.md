# Juvelle RAG Quick-Update & Administration Toolkit ⚡

A high-speed, zero-lag suite of CLI tools and Python APIs designed to update, inject, import, inspect, and manage vector knowledge collections in **Qdrant Cloud** and the **Hybrid In-Memory Vector Store** in under 1 second.

---

## 📂 Toolkit Structure

| Tool File | Purpose | Execution Speed |
| :--- | :--- | :--- |
| **[`quick_sync.py`](quick_sync.py)** | Ultra-fast sync of Microsoft Word (`.docx`) or text docs into Qdrant Cloud | `< 1000 ms` |
| **[`add_fact.py`](add_fact.py)** | Instantly inject a single product update, discount, or policy into vector DB | `< 400 ms` |
| **[`batch_import.py`](batch_import.py)** | Bulk import and vectorize multiple files (`.docx`, `.md`, `.txt`, `.json`, `.csv`) | `< 2000 ms` |
| **[`query_tester.py`](query_tester.py)** | Real-time semantic & hybrid retrieval test inspector with score breakdown | `< 150 ms` |
| **[`manage_collection.py`](manage_collection.py)** | Qdrant Cloud collection health check, point deletion, export, and wiper | `< 500 ms` |
| **[`doc_editor.py`](doc_editor.py)** | View, edit, or rebuild `Juvelle_Knowledge_Base.docx` with auto-sync | `< 800 ms` |
| **[`rag_manager.py`](rag_manager.py)** | Interactive Master Terminal Menu for running all tools in one place | Interactive |
| **[`quick_sync.bat`](quick_sync.bat)** | 1-Click Windows execution script for rapid updates | Instant |

---

## 🚀 Quickstart Commands

### 1. ⚡ Ultra-Fast Full Vector Sync
Syncs the master Microsoft Word knowledge base (`data/Juvelle_Knowledge_Base.docx`) into Qdrant Cloud:
```bash
python rag_tools/quick_sync.py
```
*Options:*
- `--file path/to/doc.docx`: Sync a custom document.
- `--recreate`: Purge and recreate the Qdrant Cloud collection before indexing.

---

### 2. ➕ Instant Single Fact Injection
Add a new rule, discount code, or FAQ directly to the vector database without opening any editor:
```bash
python rag_tools/add_fact.py --title "Onam Offer" --content "Flat 10% discount on all Churidar tops with code ONAM10." --sync-docx
```
*Options:*
- `--sync-docx`: Also appends the fact as a styled bullet point into `data/Juvelle_Knowledge_Base.docx`.

---

### 3. 📁 Bulk Import Folder of Knowledge Files
Imports and indexes all `.docx`, `.md`, `.txt`, `.json`, or `.csv` files found in a folder:
```bash
python rag_tools/batch_import.py --dir ./data
python rag_tools/batch_import.py --dir ./docs --pattern "*.md"
```

---

### 4. 🔍 Test Live Semantic Retrieval Queries
Inspect what knowledge chunks are returned for a customer query, including similarity scores, ranking, and latency:
```bash
python rag_tools/query_tester.py "do you ship to kochi?"
python rag_tools/query_tester.py "how much do churidar tops cost?" --top-k 5
python rag_tools/query_tester.py "is cash on delivery available?" --json
```

---

### 5. 📊 Qdrant Cloud Health & Collection Administration
Check collection points, list payloads, or export backups:
```bash
# Check status and vector counts
python rag_tools/manage_collection.py --status

# List stored knowledge points and payload previews
python rag_tools/manage_collection.py --list

# Delete a specific point
python rag_tools/manage_collection.py --delete-id <point_id>

# Export full backup to JSON
python rag_tools/manage_collection.py --export backup_rag.json

# Cleanly purge and reset collection
python rag_tools/manage_collection.py --clear
```

---

### 6. 🖥️ Interactive Terminal Dashboard
Launch the unified interactive terminal menu:
```bash
python rag_tools/rag_manager.py
```

---

## 🐍 Python API Usage

You can also import and use these tools programmatically in any backend service:

```python
from rag_tools import quick_sync, add_fact, test_retrieval_query, get_collection_stats

# 1. Trigger fast sync
quick_sync()

# 2. Add dynamic fact on the fly
add_fact(title="Express Delivery", content="1-day express delivery available in Ernakulam.")

# 3. Test retrieval
chunks = test_retrieval_query("How fast is delivery in Kochi?")

# 4. Check cluster status
stats = get_collection_stats()
print(f"Total indexed vectors: {stats['points_count']}")
```
