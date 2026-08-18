import sqlite3
import logging
from typing import List, Dict, Any
from ingestion.spark_session import get_spark_session
from memory.long_term_memory import DB_PATH, update_user_profile

logger = logging.getLogger("SparkMemoryConsolidator")

def consolidate_user_memories_spark() -> int:
    """
    Executes a local Apache Spark job (100% Free) to analyze historical conversation logs,
    aggregate user dialogue patterns, and update long-term semantic memory profiles.
    """
    logger.info("Starting local Spark episodic memory consolidation job...")
    
    # 1. Connect to SQLite and extract conversation records
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT turn_id, session_id, user_id, role, content FROM conversation_turns WHERE role = 'user'")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        logger.info("No conversation logs found to consolidate.")
        return 0

    spark = get_spark_session("SparkMemoryConsolidator")

    # 2. Build Spark DataFrame
    turn_records = [
        {"turn_id": r[0], "session_id": r[1], "user_id": r[2], "role": r[3], "content": r[4]}
        for r in rows
    ]
    df_turns = spark.createDataFrame(turn_records)

    # 3. Group by user_id and aggregate dialogue
    try:
        from pyspark.sql.functions import col, collect_list, concat_ws
        df_aggregated = (
            df_turns.groupBy("user_id")
            .agg(
                collect_list("content").alias("user_messages"),
                concat_ws(" | ", collect_list("content")).alias("merged_history")
            )
        )
    except Exception:
        df_aggregated = df_turns.groupBy("user_id").agg()

    results = df_aggregated.collect()
    consolidated_count = 0

    for row in results:
        u_id = row.get("user_id") if isinstance(row, dict) else row.user_id
        messages = row.get("user_messages") if isinstance(row, dict) else row.user_messages
        merged = row.get("merged_history") if isinstance(row, dict) else row.merged_history
        
        # Extract keywords and summary
        words = merged.lower().split()
        stopwords = {"the", "a", "an", "is", "in", "it", "to", "of", "for", "and", "or", "on", "what", "how", "why", "i", "you"}
        filtered_words = [w.strip("?,.!") for w in words if w.strip("?,.!") not in stopwords and len(w) > 3]
        
        from collections import Counter
        top_topics = [word for word, _ in Counter(filtered_words).most_common(5)]
        
        summary = f"User has engaged in {len(messages)} interaction turns. Frequent focus areas: {', '.join(top_topics) if top_topics else 'General Inquiries'}."
        
        # Update SQLite Long-Term Memory Profile
        update_user_profile(user_id=u_id, profile_summary=summary, key_topics=top_topics)
        consolidated_count += 1
        logger.info(f"Consolidated profile for user '{u_id}': {summary}")

    logger.info(f"Completed Spark memory consolidation for {consolidated_count} user profiles.")
    return consolidated_count

if __name__ == "__main__":
    consolidate_user_memories_spark()
