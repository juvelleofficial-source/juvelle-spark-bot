import sqlite3
import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "memory.db")

def init_memory_db() -> None:
    """
    Initializes local SQLite tables for long-term episodic conversation history,
    user profiles, and customer CRM intelligence (100% Free).
    """
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Episodic Conversation Logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversation_turns (
        turn_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        citations TEXT,
        model_used TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Consolidated Long-Term User Profiles
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT PRIMARY KEY,
        profile_summary TEXT NOT NULL,
        key_topics TEXT,
        interaction_count INTEGER DEFAULT 1,
        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Customer CRM Intelligence & Filtering Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customer_crm (
        user_id TEXT PRIMARY KEY,
        preferred_size TEXT,
        preferred_fabric TEXT,
        preferred_language TEXT DEFAULT 'english',
        location TEXT,
        stage TEXT DEFAULT 'New Lead',
        total_turns INTEGER DEFAULT 1,
        last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
        tags TEXT,
        notes TEXT
    )
    """)
    try:
        cursor.execute("ALTER TABLE customer_crm ADD COLUMN preferred_language TEXT DEFAULT 'english'")
    except Exception:
        pass

    conn.commit()
    conn.close()

    logger.info(f"Initialized local SQLite memory & CRM store at {DB_PATH}")

def log_conversation_turn(
    turn_id: str,
    session_id: str,
    user_id: str,
    role: str,
    content: str,
    citations: Optional[List[Dict[str, Any]]] = None,
    model_used: Optional[str] = None
) -> None:
    """
    Persists a single conversation turn into SQLite.
    """
    init_memory_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    citations_json = json.dumps(citations) if citations else None
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
    INSERT OR REPLACE INTO conversation_turns (turn_id, session_id, user_id, role, content, citations, model_used, timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (turn_id, session_id, user_id, role, content, citations_json, model_used, now_iso))

    conn.commit()
    conn.close()

def get_session_history(session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retrieves past turns for a specific session ordered chronologically.
    """
    init_memory_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT turn_id, session_id, user_id, role, content, citations, model_used, timestamp
    FROM conversation_turns
    WHERE session_id = ?
    ORDER BY timestamp ASC
    LIMIT ?
    """, (session_id, limit))

    rows = cursor.fetchall()
    conn.close()

    history = []
    for r in rows:
        history.append({
            "turn_id": r[0],
            "session_id": r[1],
            "user_id": r[2],
            "role": r[3],
            "content": r[4],
            "citations": json.loads(r[5]) if r[5] else [],
            "model_used": r[6],
            "timestamp": r[7]
        })
    return history

def get_user_turns_count(user_id: str) -> int:
    """
    Returns the total number of turns recorded for a user across all sessions.
    """
    init_memory_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM conversation_turns WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_last_turn_timestamp(user_id: str, session_id: Optional[str] = None) -> Optional[float]:
    """
    Returns the Unix timestamp (seconds since epoch) of the most recent conversation turn
    for a given user_id (and optionally session_id), or None if no prior turns exist.
    """
    init_memory_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if session_id:
        cursor.execute("SELECT timestamp FROM conversation_turns WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1", (session_id,))
    else:
        cursor.execute("SELECT timestamp FROM conversation_turns WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    try:
        ts_str = row[0]
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return None


def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves long-term consolidated profile for a user.
    """
    init_memory_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT user_id, profile_summary, key_topics, interaction_count, last_updated
    FROM user_profiles
    WHERE user_id = ?
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "user_id": row[0],
        "profile_summary": row[1],
        "key_topics": json.loads(row[2]) if row[2] else [],
        "interaction_count": row[3],
        "last_updated": row[4]
    }

def update_user_profile(user_id: str, profile_summary: str, key_topics: List[str]) -> None:
    """
    Updates or inserts a user's consolidated profile.
    """
    init_memory_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    topics_json = json.dumps(key_topics)
    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
    INSERT INTO user_profiles (user_id, profile_summary, key_topics, interaction_count, last_updated)
    VALUES (?, ?, ?, 1, ?)
    ON CONFLICT(user_id) DO UPDATE SET
        profile_summary = excluded.profile_summary,
        key_topics = excluded.key_topics,
        interaction_count = user_profiles.interaction_count + 1,
        last_updated = excluded.last_updated
    """, (user_id, profile_summary, topics_json, now_iso))

    conn.commit()
    conn.close()

# ==========================================
# CUSTOMER CRM & FILTERING OPERATIONS
# ==========================================

def upsert_customer_crm(
    user_id: str,
    preferred_size: Optional[str] = None,
    preferred_fabric: Optional[str] = None,
    preferred_language: Optional[str] = None,
    location: Optional[str] = None,
    stage: Optional[str] = None,
    tags: Optional[List[str]] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates or updates structured CRM intelligence for a customer.
    """
    init_memory_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("SELECT preferred_size, preferred_fabric, preferred_language, location, stage, total_turns, tags, notes FROM customer_crm WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if row:
        curr_size, curr_fabric, curr_lang, curr_loc, curr_stage, curr_turns, curr_tags_str, curr_notes = row
        new_size = preferred_size or curr_size
        new_fabric = preferred_fabric or curr_fabric
        new_lang = preferred_language or curr_lang or "english"
        new_loc = location or curr_loc
        new_stage = stage or curr_stage
        new_turns = curr_turns + 1

        existing_tags = json.loads(curr_tags_str) if curr_tags_str else []
        if tags:
            combined_tags = list(set(existing_tags + tags))
        else:
            combined_tags = existing_tags

        new_notes = notes if notes is not None else curr_notes

        cursor.execute("""
        UPDATE customer_crm
        SET preferred_size = ?, preferred_fabric = ?, preferred_language = ?, location = ?, stage = ?,
            total_turns = ?, last_active = ?, tags = ?, notes = ?
        WHERE user_id = ?
        """, (new_size, new_fabric, new_lang, new_loc, new_stage, new_turns, now_iso, json.dumps(combined_tags), new_notes, user_id))
    else:
        new_size = preferred_size
        new_fabric = preferred_fabric
        new_lang = preferred_language or "english"
        new_loc = location
        new_stage = stage or "New Lead"
        new_turns = 1
        combined_tags = tags or []
        new_notes = notes or ""

        cursor.execute("""
        INSERT INTO customer_crm (user_id, preferred_size, preferred_fabric, preferred_language, location, stage, total_turns, last_active, tags, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, new_size, new_fabric, new_lang, new_loc, new_stage, new_turns, now_iso, json.dumps(combined_tags), new_notes))

    conn.commit()
    conn.close()

    return {
        "user_id": user_id,
        "preferred_size": new_size,
        "preferred_fabric": new_fabric,
        "preferred_language": new_lang,
        "location": new_loc,
        "stage": new_stage,
        "total_turns": new_turns,
        "tags": combined_tags,
        "last_active": now_iso
    }

def get_customer_crm(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches full CRM dossier for a specific customer.
    """
    init_memory_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT user_id, preferred_size, preferred_fabric, preferred_language, location, stage, total_turns, last_active, tags, notes
    FROM customer_crm
    WHERE user_id = ?
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "user_id": row[0],
        "preferred_size": row[1],
        "preferred_fabric": row[2],
        "preferred_language": row[3] or "english",
        "location": row[4],
        "stage": row[5],
        "total_turns": row[6],
        "last_active": row[7],
        "tags": json.loads(row[8]) if row[8] else [],
        "notes": row[9]
    }


def list_customers_crm(
    stage: Optional[str] = None,
    preferred_size: Optional[str] = None,
    location: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Filters and organizes customer profiles by lifecycle stage, size, and location.
    """
    init_memory_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = "SELECT user_id, preferred_size, preferred_fabric, location, stage, total_turns, last_active, tags, notes FROM customer_crm WHERE 1=1"
    params = []

    if stage:
        query += " AND stage = ?"
        params.append(stage)
    if preferred_size:
        query += " AND preferred_size = ?"
        params.append(preferred_size.upper())
    if location:
        query += " AND location LIKE ?"
        params.append(f"%{location}%")

    query += " ORDER BY last_active DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    customers = []
    for r in rows:
        customers.append({
            "user_id": r[0],
            "preferred_size": r[1],
            "preferred_fabric": r[2],
            "location": r[3],
            "stage": r[4],
            "total_turns": r[5],
            "last_active": r[6],
            "tags": json.loads(r[7]) if r[7] else [],
            "notes": r[8]
        })
    return customers

def get_crm_stats() -> Dict[str, Any]:
    """
    Aggregates CRM analytics (total customers, breakdown by stage, popular sizes).
    """
    init_memory_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM customer_crm")
    total_customers = cursor.fetchone()[0]

    cursor.execute("SELECT stage, COUNT(*) FROM customer_crm GROUP BY stage")
    stage_breakdown = dict(cursor.fetchall())

    cursor.execute("SELECT preferred_size, COUNT(*) FROM customer_crm WHERE preferred_size IS NOT NULL GROUP BY preferred_size")
    size_breakdown = dict(cursor.fetchall())

    conn.close()
    return {
        "total_customers": total_customers,
        "stages": stage_breakdown,
        "popular_sizes": size_breakdown
    }
