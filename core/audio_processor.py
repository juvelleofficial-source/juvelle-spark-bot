import os
import io
import urllib.request
import logging
from typing import Optional
from google import genai
from google.genai import types

logger = logging.getLogger("AudioProcessor")

def download_audio_bytes(audio_url: str) -> Optional[bytes]:
    """Downloads audio/voice note stream bytes from Meta CDN URL."""
    try:
        req = urllib.request.Request(
            audio_url,
            headers={"User-Agent": "JuvelleAudioBot/2.2"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except Exception as e:
        logger.error(f"Failed to download audio from {audio_url}: {e}")
        return None

def transcribe_and_understand_voice_note(audio_bytes: bytes, mime_type: str = "audio/mp4") -> str:
    """
    Transcribes and understands voice notes in any language (Malayalam, Manglish, Hindi, Tamil, English)
    using Gemini Multimodal Audio processing.
    """
    if not audio_bytes:
        return ""
        
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set. Cannot transcribe audio.")
        return ""
        
    try:
        client = genai.Client(api_key=api_key)
        
        # Ingest audio bytes directly into Gemini Multimodal LLM
        prompt = (
            "You are an expert multilingual audio transcription engine. "
            "Listen to this customer audio/voice message. "
            "Transcribe the customer's spoken words accurately in the language or script spoken "
            "(e.g., Malayalam, Manglish, Hindi, Tamil, English). "
            "Return ONLY the verbatim spoken message as text without preamble or commentary."
        )
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                prompt
            ]
        )
        
        transcribed_text = response.text.strip() if response and response.text else ""
        logger.info(f"Successfully transcribed voice note: '{transcribed_text}'")
        return transcribed_text
    except Exception as e:
        logger.error(f"Voice note transcription error: {e}")
        # Try fallback model
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    "Transcribe what is spoken in this audio accurately. Return only the transcription."
                ]
            )
            return response.text.strip() if response and response.text else ""
        except Exception as e2:
            logger.error(f"Fallback audio transcription error: {e2}")
            return ""
