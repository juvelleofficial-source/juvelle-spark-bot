import os
import io
import urllib.request
import logging
from typing import Optional, Tuple
from google import genai
from google.genai import types

logger = logging.getLogger("AudioProcessor")

def detect_audio_mime_type(audio_bytes: bytes) -> str:
    """
    Identifies audio codec and container format from raw byte headers in milliseconds.
    Supports MP4/M4A/AAC, OGG, WAV, MP3, WebM, and FLAC.
    """
    if not audio_bytes or len(audio_bytes) < 12:
        return "audio/mp4"
        
    # Check Magic Bytes
    if audio_bytes[:4] == b"OggS":
        return "audio/ogg"
    if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return "audio/wav"
    if audio_bytes[:3] == b"ID3" or (audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0):
        return "audio/mp3"
    if audio_bytes[4:8] == b"ftyp":
        return "audio/mp4"
    if audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
        return "audio/webm"
    if audio_bytes[:4] == b"fLaC":
        return "audio/flac"
        
    # Default fallback for Instagram CDN voice notes
    return "audio/mp4"

def download_audio_bytes(audio_url: str) -> Optional[Tuple[bytes, str]]:
    """
    Downloads audio/voice note stream bytes from Meta CDN URL and detects codec/MIME.
    Returns (raw_bytes, detected_mime_type).
    """
    try:
        req = urllib.request.Request(
            audio_url,
            headers={"User-Agent": "JuvelleAudioBot/2.2"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
            
            # Detect MIME
            if "ogg" in content_type:
                mime = "audio/ogg"
            elif "aac" in content_type:
                mime = "audio/aac"
            elif "wav" in content_type:
                mime = "audio/wav"
            elif "mp3" in content_type or "mpeg" in content_type:
                mime = "audio/mp3"
            elif "mp4" in content_type or "m4a" in content_type:
                mime = "audio/mp4"
            else:
                mime = detect_audio_mime_type(data)
                
            logger.info(f"Downloaded {len(data)} bytes audio (MIME: {mime}, Content-Type: {content_type})")
            return data, mime
    except Exception as e:
        logger.error(f"Failed to download audio from {audio_url}: {e}")
        return None

def transcribe_and_understand_voice_note(audio_bytes: bytes, mime_type: Optional[str] = None) -> str:
    """
    Transcribes and understands voice notes in any language (Malayalam, Manglish, Hindi, Tamil, English)
    using Gemini Multimodal Audio processing in sub-second latency.
    """
    if not audio_bytes:
        return ""
        
    if not mime_type:
        mime_type = detect_audio_mime_type(audio_bytes)
        
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set. Cannot transcribe audio.")
        return ""
        
    try:
        client = genai.Client(api_key=api_key)
        
        prompt = (
            "You are an expert multilingual audio perception and transcription engine for Instagram DMs. "
            "Listen to this customer voice note. "
            "Accurately transcribe the spoken words in the exact language/script spoken "
            "(Malayalam, Manglish, English, Tamil, Hindi). "
            "Return ONLY the verbatim transcription without preambles or quotes."
        )
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                prompt
            ]
        )
        
        transcribed_text = response.text.strip() if response and response.text else ""
        logger.info(f"Successfully transcribed voice note ({mime_type}): '{transcribed_text}'")
        return transcribed_text
    except Exception as e:
        logger.error(f"Gemini 2.0 Flash voice transcription notice: {e}")
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    "Transcribe the spoken audio message accurately. Return only transcription."
                ]
            )
            return response.text.strip() if response and response.text else ""
        except Exception as e2:
            logger.error(f"Fallback audio transcription notice: {e2}")
            return ""

def process_voice_message(
    audio_bytes: bytes,
    mime_type: Optional[str] = None,
    session_id: str = "default_user",
    customer_name: Optional[str] = None
) -> dict:
    """
    End-to-end voice message processing:
    1. Transcribes audio via Gemini Multimodal.
    2. Runs reasoning / RAG pipeline.
    3. Returns structured output for API consumers.
    """
    from core.juvelle_agent import generate_juvelle_response

    transcript = transcribe_and_understand_voice_note(audio_bytes, mime_type)
    if not transcript:
        return {
            "transcript": "",
            "detected_language": "unknown",
            "reply_text": "Thank you for reaching out to Juvelle! Could you please repeat that or send a text message?",
            "audio_data": None,
            "has_audio_reply": False,
            "session_id": session_id
        }

    responses = generate_juvelle_response(
        chat_input=transcript,
        session_id=session_id,
        user_id=session_id
    )

    reply_text = "\n".join(responses) if isinstance(responses, list) else str(responses)

    return {
        "transcript": transcript,
        "detected_language": "auto",
        "reply_text": reply_text,
        "audio_data": None,
        "has_audio_reply": False,
        "session_id": session_id
    }
