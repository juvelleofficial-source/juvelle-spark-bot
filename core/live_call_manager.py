import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect

from core.juvelle_agent import generate_juvelle_reply, detect_query_language
from core.audio_processor import generate_tts_base64, transcribe_audio_with_gemini

logger = logging.getLogger("LiveCallManager")

class LiveCallSession:
    """Represents an isolated, active real-time live audio call session."""

    def __init__(self, session_id: str, websocket: WebSocket):
        self.session_id = session_id
        self.websocket = websocket
        self.start_time = time.time()
        self.is_active = True
        self.preferred_language = "english"
        self.turn_count = 0

    async def send_event(self, event_type: str, data: Dict[str, Any]):
        """Sends a structured JSON packet to the client."""
        if not self.is_active:
            return
        payload = {
            "type": event_type,
            "session_id": self.session_id,
            "timestamp": time.time(),
            **data
        }
        await self.websocket.send_text(json.dumps(payload))

    async def handle_user_text(self, text: str):
        """Processes an incoming text-simulated speech turn during a live call."""
        if not text or not text.strip():
            return
        self.turn_count += 1
        lang = detect_query_language(text)
        self.preferred_language = lang

        # 1. Emit user caption
        await self.send_event("user_speech", {
            "transcript": text.strip(),
            "language": lang
        })

        # 2. Generate conversational AI reply with RAG
        await self.send_event("status", {"state": "speaking", "message": "Juvelle is replying..."})
        reply_text = generate_juvelle_reply(
            customer_message=text.strip(),
            session_id=self.session_id
        )

        # 3. Generate TTS audio for live playback
        audio_b64 = generate_tts_base64(reply_text, language=lang)

        # 4. Send bot speech and audio payload
        await self.send_event("bot_speech", {
            "text": reply_text,
            "audio_data": audio_b64,
            "language": lang
        })
        
        await self.send_event("status", {"state": "active", "message": "Call active"})

    async def handle_user_audio(self, audio_bytes: bytes, mime_type: str = "audio/webm"):
        """Processes an incoming live voice segment from the caller."""
        if mime_type.startswith("text/"):
            await self.handle_user_text(audio_bytes.decode('utf-8', errors='ignore'))
            return

        self.turn_count += 1
        
        # 1. Transcribe speech
        await self.send_event("status", {"state": "listening", "message": "Transcribing speech..."})
        transcription_res = transcribe_audio_with_gemini(audio_bytes, mime_type=mime_type)
        transcript = transcription_res["transcript"]
        lang = transcription_res["detected_language"]
        self.preferred_language = lang

        # 2. Emit user caption
        await self.send_event("user_speech", {
            "transcript": transcript,
            "language": lang
        })

        # 3. Generate conversational AI reply with RAG
        await self.send_event("status", {"state": "speaking", "message": "Juvelle is replying..."})
        reply_text = generate_juvelle_reply(
            customer_message=transcript,
            session_id=self.session_id
        )

        # 4. Generate TTS audio for live playback
        audio_b64 = generate_tts_base64(reply_text, language=lang)

        # 5. Send bot speech and audio payload
        await self.send_event("bot_speech", {
            "text": reply_text,
            "audio_data": audio_b64,
            "language": lang
        })
        
        await self.send_event("status", {"state": "active", "message": "Call active"})

class LiveCallManager:
    """
    Central connection manager supporting unlimited concurrent live call sessions.
    Every session runs asynchronously and independently.
    """

    def __init__(self):
        self.active_sessions: Dict[str, LiveCallSession] = {}
        self.lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> LiveCallSession:
        await websocket.accept()
        session = LiveCallSession(session_id, websocket)
        async with self.lock:
            self.active_sessions[session_id] = session
        logger.info(f"Live call session connected: {session_id} (Active calls: {len(self.active_sessions)})")
        
        # Send initial connection handshake
        await session.send_event("connected", {
            "message": "Connected to Juvelle AI Live Call",
            "active_call_count": len(self.active_sessions)
        })
        
        # Initial greeting in live call
        initial_greeting = "Hello! Welcome to Juvelle Boutique. How can I help you today?"
        greeting_audio = generate_tts_base64(initial_greeting, language="english")
        await session.send_event("bot_speech", {
            "text": initial_greeting,
            "audio_data": greeting_audio,
            "language": "english"
        })
        
        return session

    async def disconnect(self, session_id: str):
        async with self.lock:
            if session_id in self.active_sessions:
                session = self.active_sessions.pop(session_id)
                session.is_active = False
                logger.info(f"Live call session disconnected: {session_id} (Active calls: {len(self.active_sessions)})")

    def get_session(self, session_id: str) -> Optional[LiveCallSession]:
        return self.active_sessions.get(session_id)

    def get_active_count(self) -> int:
        return len(self.active_sessions)

live_call_manager = LiveCallManager()
