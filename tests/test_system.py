import unittest
import uuid
import os
import shutil
from ingestion.spark_session import get_spark_session
from ingestion.document_processor import process_documents_distributed
from ingestion.batch_embedder import generate_embeddings_distributed
import ingestion.vector_indexer as vector_indexer
from ingestion.ingestion_job import run_ingestion_pipeline, create_sample_documents
from retrieval.vector_retriever import retrieve_hybrid_context, bm25_lexical_search
from memory.short_term_memory import ShortTermMemoryManager
from memory.long_term_memory import init_memory_db, get_session_history, get_user_profile, DB_PATH
from memory.spark_memory_consolidator import consolidate_user_memories_spark
from core.router import route_query_intent
from core.orchestrator import orchestrator

class TestGeminiSparkSystem(unittest.TestCase):

    def test_spark_session_init(self):
        """Verify local Spark session builds properly."""
        spark = get_spark_session("TestSparkSession")
        self.assertIsNotNone(spark)
        self.assertIn("local", spark.conf.get("spark.master"))

    def test_spark_document_chunking(self):
        """Verify distributed document chunking."""
        spark = get_spark_session("TestChunking")
        sample_docs = create_sample_documents()
        df_raw = spark.createDataFrame(sample_docs)
        
        df_chunks = process_documents_distributed(df_raw, chunk_size=50, chunk_overlap=10)
        self.assertGreater(df_chunks.count(), 0)
        
        first_row = df_chunks.first()
        chunk_id = first_row.get("chunk_id") if isinstance(first_row, dict) else first_row.chunk_id
        content = first_row.get("content") if isinstance(first_row, dict) else first_row.content
        token_count = first_row.get("token_count") if isinstance(first_row, dict) else first_row.token_count
        
        self.assertIsNotNone(chunk_id)
        self.assertIsNotNone(content)
        self.assertGreater(token_count, 0)

    def test_spark_ingestion_and_vector_search(self):
        """Verify end-to-end Spark ETL ingestion and vector search."""
        synced_count = run_ingestion_pipeline()
        self.assertGreater(synced_count, 0)
        self.assertEqual(len(vector_indexer._LOCAL_VECTOR_STORE), synced_count)

        # Test Hybrid Vector Retrieval
        results = retrieve_hybrid_context("churidar tops fabric and price", top_k=3)
        self.assertGreater(len(results), 0)
        self.assertTrue(any("content" in r and len(r["content"]) > 0 for r in results))

    def test_dual_tier_memory(self):
        """Verify in-memory sliding window and SQLite persistent logging."""
        mem_mgr = ShortTermMemoryManager(window_size=3)
        session_id = f"test_sess_{uuid.uuid4().hex[:8]}"
        user_id = f"test_usr_{uuid.uuid4().hex[:8]}"

        # Add 4 turns (exceeding window_size of 3)
        mem_mgr.add_turn(session_id, user_id, "user", "Hello first")
        mem_mgr.add_turn(session_id, user_id, "assistant", "Hi first")
        mem_mgr.add_turn(session_id, user_id, "user", "What is Spark?")
        mem_mgr.add_turn(session_id, user_id, "assistant", "Spark is a distributed engine.")

        # Short-term cache should only have last 3 turns
        active_window = mem_mgr.get_context_window(session_id)
        self.assertEqual(len(active_window), 3)
        self.assertEqual(active_window[-1]["content"], "Spark is a distributed engine.")

        # Long-term SQLite should have all 4 turns
        db_history = get_session_history(session_id, limit=10)
        self.assertEqual(len(db_history), 4)

    def test_spark_memory_consolidation(self):
        """Verify local Spark memory consolidation over SQLite logs."""
        consolidated_count = consolidate_user_memories_spark()
        self.assertGreaterEqual(consolidated_count, 1)

    def test_router_intents(self):
        """Verify query intent classification."""
        intent_greet, _ = route_query_intent("Hello there!")
        self.assertEqual(intent_greet, "CHIT_CHAT")

        intent_rag, _ = route_query_intent("What is the memory protocol for enterprise chatbots?")
        self.assertEqual(intent_rag, "RAG_QUERY")

        intent_deep, _ = route_query_intent("Please compare the architecture tradeoffs between Dataproc and local PySpark step by step.")
        self.assertEqual(intent_deep, "DEEP_REASONING")

    def test_orchestrator_stream(self):
        """Verify end-to-end orchestrator streaming and citation output."""
        unique_sess = f"stream_test_{uuid.uuid4().hex[:8]}"
        unique_usr = f"stream_usr_{uuid.uuid4().hex[:8]}"
        
        events = list(orchestrator.process_chat_stream(
            user_query="Explain the security and access control policies in RAG.",
            session_id=unique_sess,
            user_id=unique_usr
        ))
        
        event_types = [e["event"] for e in events]
        self.assertIn("metadata", event_types)
        self.assertIn("token", event_types)
        self.assertIn("done", event_types)

if __name__ == "__main__":
    unittest.main()
