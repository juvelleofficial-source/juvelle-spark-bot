#!/usr/bin/env python3
"""
Unit & Integration Tests for Juvelle RAG Toolkit
================================================
Verifies quick_sync, add_fact, batch_import, query_tester, and manage_collection.
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from rag_tools.quick_sync import quick_sync
from rag_tools.add_fact import add_fact
from rag_tools.query_tester import test_retrieval_query
from rag_tools.manage_collection import get_collection_stats, list_collection_points

class TestRAGTools(unittest.TestCase):

    def test_01_quick_sync(self):
        """Test ultra-fast knowledge synchronization."""
        indexed_count = quick_sync(verbose=False)
        self.assertGreater(indexed_count, 0, "Quick sync should index at least 1 chunk.")

    def test_02_add_fact(self):
        """Test on-the-fly single fact injection."""
        chunk_id = add_fact(
            title="Unit Test Fact",
            content="Juvelle offers custom gift packaging for festive orders.",
            verbose=False
        )
        self.assertTrue(chunk_id.startswith("FACT_"), "Chunk ID should start with FACT_")

    def test_03_query_tester(self):
        """Test semantic retrieval tester."""
        results = test_retrieval_query(
            query="gift packaging",
            top_k=2,
            verbose=False
        )
        self.assertIsInstance(results, list, "Retrieval should return a list of chunks.")
        self.assertGreater(len(results), 0, "Should retrieve at least 1 relevant chunk.")

    def test_04_collection_stats(self):
        """Test collection stats inspection."""
        stats = get_collection_stats(verbose=False)
        self.assertIn("collection_name", stats)
        self.assertIn("points_count", stats)

if __name__ == "__main__":
    unittest.main()
