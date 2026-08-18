import sqlite3
import os
import json
import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "mcp_inbox.db")

def init_mcp_inbox_db() -> None:
    """Initializes SQLite database for Facebook/Meta incoming messages and MCP queue."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS facebook_messages (
        message_id TEXT PRIMARY KEY,
        sender_id TEXT NOT NULL,
        sender_name TEXT,
        platform TEXT DEFAULT 'messenger',
        message_text TEXT NOT NULL,
        status TEXT DEFAULT 'pending', -- pending, replied, dismissed
        ai_reply TEXT,
        received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        replied_at DATETIME
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customer_crm_notes (
        sender_id TEXT PRIMARY KEY,
        customer_name TEXT,
        profile_notes TEXT,
        last_interaction DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

def enqueue_facebook_message(sender_id: str, message_text: str, sender_name: Optional[str] = None, platform: str = "messenger") -> str:
    """Enqueues an incoming message received via Meta Webhook."""
    init_mcp_inbox_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    msg_id = f"fb_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
    INSERT INTO facebook_messages (message_id, sender_id, sender_name, platform, message_text, status, received_at)
    VALUES (?, ?, ?, ?, ?, 'pending', ?)
    """, (msg_id, sender_id, sender_name or "Facebook User", platform, message_text, now_iso))

    conn.commit()
    conn.close()
    logger.info(f"Enqueued Facebook message [{msg_id}] from {sender_id}: '{message_text[:40]}...'")
    return msg_id

def get_pending_messages(limit: int = 10) -> List[Dict[str, Any]]:
    """Fetches unreplied customer messages for Gemini Spark to process."""
    init_mcp_inbox_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT message_id, sender_id, sender_name, platform, message_text, received_at
    FROM facebook_messages
    WHERE status = 'pending'
    ORDER BY received_at ASC
    LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "message_id": r[0],
            "sender_id": r[1],
            "sender_name": r[2],
            "platform": r[3],
            "message_text": r[4],
            "received_at": r[5]
        }
        for r in rows
    ]

def mark_message_replied(message_id: str, ai_reply: str) -> None:
    """Marks a message as replied in the queue."""
    init_mcp_inbox_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
    UPDATE facebook_messages
    SET status = 'replied', ai_reply = ?, replied_at = ?
    WHERE message_id = ?
    """, (ai_reply, now_iso, message_id))

    conn.commit()
    conn.close()

def get_message_reply(message_id: str) -> Optional[str]:
    """Checks if a message has received an AI reply from Gemini Spark."""
    init_mcp_inbox_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT ai_reply FROM facebook_messages WHERE message_id = ? AND status = 'replied'", (message_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def save_crm_note(sender_id: str, customer_name: str, profile_notes: str) -> None:
    """Saves customer notes into persistent CRM memory."""
    init_mcp_inbox_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
    INSERT INTO customer_crm_notes (sender_id, customer_name, profile_notes, last_interaction)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(sender_id) DO UPDATE SET
        customer_name = excluded.customer_name,
        profile_notes = excluded.profile_notes,
        last_interaction = excluded.last_interaction
    """, (sender_id, customer_name, profile_notes, now_iso))

    conn.commit()
    conn.close()
