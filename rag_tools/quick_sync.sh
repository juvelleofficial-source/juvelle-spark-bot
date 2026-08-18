#!/usr/bin/env bash
# =========================================================================
# Juvelle RAG Quick Sync 1-Click Shell Script
# =========================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
python3 rag_tools/quick_sync.py "$@"
