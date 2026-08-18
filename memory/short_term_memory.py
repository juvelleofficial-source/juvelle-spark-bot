import time
import logging
from typing import List, Dict, Any, Optional
from collections import defaultdict
from memory.long_term_memory import log_conversation_turn, get_session_history, get_user_turns_count, get_last_turn_timestamp

logger = logging.getLogger(__name__)

# In-Memory Fast Cache: session_id -> list of turn dicts
_MEMORY_CACHE: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
_SESSION_META: Dict[str, Dict[str, Any]] = {}
_MAX_WINDOW_TURNS = 10
_SESSION_INACTIVITY_TIMEOUT = 10800  # 3 hours in seconds (10,800s)

class ShortTermMemoryManager:
    """
    Manages conversational session lifecycle, time-aware greetings,
    and sub-millisecond in-memory working context with persistent SQLite sync.
    """

    def __init__(self, window_size: int = _MAX_WINDOW_TURNS, timeout_seconds: int = _SESSION_INACTIVITY_TIMEOUT):
        self.window_size = window_size
        self.timeout_seconds = timeout_seconds

    def evaluate_session_lifecycle(self, session_id: str, user_id: str) -> Dict[str, Any]:
        """
        Determines the exact conversational lifecycle state:
        - 'first_contact': Brand new user, 0 prior interactions -> Deliver Full Warm Welcome.
        - 'returning_session': Inactive for > 3 hours -> Deliver Welcome Back Re-engagement.
        - 'active_ongoing': Active within < 3 hours -> Maintain flow, ZERO repeated greetings.
        """
        now = time.time()
        meta = _SESSION_META.get(session_id)

        if not meta:
            # Check SQLite if this user/session had past conversations and check last turn timestamp
            last_ts = get_last_turn_timestamp(user_id=user_id, session_id=session_id)
            past_total_turns = get_user_turns_count(user_id)

            if past_total_turns == 0 or last_ts is None:
                lifecycle_state = "first_contact"
                is_first = True
                turn_cnt = 1
                idle_sec = 0
            else:
                idle_sec = int(now - last_ts)
                if idle_sec <= self.timeout_seconds:
                    # Prior interaction within 3 hours -> Active ongoing session
                    lifecycle_state = "active_ongoing"
                    is_first = False
                    turn_cnt = past_total_turns + 1
                else:
                    # Inactive > 3 hours -> Returning customer session
                    lifecycle_state = "returning_session"
                    is_first = True
                    turn_cnt = 1

            _SESSION_META[session_id] = {
                "first_seen": now,
                "last_active": now,
                "turn_count": turn_cnt,
                "session_start_time": now,
                "lifecycle_state": lifecycle_state
            }
            return {
                "lifecycle_state": lifecycle_state,
                "is_first_turn_of_session": is_first,
                "turn_count": turn_cnt,
                "idle_seconds": idle_sec
            }

        # Existing active in-memory session metadata
        idle_seconds = now - meta["last_active"]
        
        if idle_seconds > self.timeout_seconds:
            # Session expired -> New returning session
            lifecycle_state = "returning_session"
            meta["session_start_time"] = now
            meta["turn_count"] = 1
            meta["lifecycle_state"] = lifecycle_state
            meta["last_active"] = now
            is_first_turn_of_session = True
        else:
            # Active ongoing session within 30 minutes
            lifecycle_state = "active_ongoing"
            meta["turn_count"] += 1
            meta["lifecycle_state"] = lifecycle_state
            meta["last_active"] = now
            is_first_turn_of_session = False

        return {
            "lifecycle_state": lifecycle_state,
            "is_first_turn_of_session": is_first_turn_of_session,
            "turn_count": meta["turn_count"],
            "idle_seconds": int(idle_seconds)
        }

    def add_turn(
        self,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        citations: Optional[List[Dict[str, Any]]] = None,
        model_used: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Appends a turn to in-memory working cache and persists to SQLite.
        """
        turn_id = f"turn_{int(time.time() * 1000)}"
        now_ts = time.time()
        turn_data = {
            "turn_id": turn_id,
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "citations": citations or [],
            "model_used": model_used or "gemini-flash-lite-latest",
            "timestamp": now_ts
        }

        # 1. Update In-Memory Cache with sliding window
        session_turns = _MEMORY_CACHE[session_id]
        session_turns.append(turn_data)
        if len(session_turns) > self.window_size:
            _MEMORY_CACHE[session_id] = session_turns[-self.window_size:]

        # 2. Update session metadata timestamp
        if session_id in _SESSION_META:
            _SESSION_META[session_id]["last_active"] = now_ts

        # 3. Persist to SQLite long-term storage
        try:
            log_conversation_turn(
                turn_id=turn_id,
                session_id=session_id,
                user_id=user_id,
                role=role,
                content=content,
                citations=citations,
                model_used=model_used
            )
        except Exception as e:
            logger.error(f"Failed to log turn to SQLite: {e}")

        return turn_data

    def get_context_window(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Returns recent active dialogue turns for the prompt context.
        If cache is empty (e.g. server restart), loads from SQLite.
        """
        if session_id in _MEMORY_CACHE and _MEMORY_CACHE[session_id]:
            return _MEMORY_CACHE[session_id]

        # Hydrate from SQLite
        db_history = get_session_history(session_id, limit=self.window_size)
        if db_history:
            _MEMORY_CACHE[session_id] = db_history
            return db_history

        return []

    def get_active_sessions_count(self) -> int:
        """Returns number of active tracked sessions."""
        return len(_SESSION_META)

    def clear_session(self, session_id: str) -> None:
        """Clears working cache and metadata for a session."""
        if session_id in _MEMORY_CACHE:
            del _MEMORY_CACHE[session_id]
        if session_id in _SESSION_META:
            del _SESSION_META[session_id]

memory_manager = ShortTermMemoryManager()
