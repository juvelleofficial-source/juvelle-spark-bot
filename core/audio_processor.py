import os
import io
import re
import base64
import logging
from typing import Dict, Any, Optional
from google import genai
from google.genai import types
from gtts import gTTS

from config.settings import settings
from config.brand_profile import BRAND_PROFILE
from core.juvelle_agent import get_genai_client, generate_juvelle_reply, detect_query_language
from retrieval.vector_retriever import retrieve_hybrid_context
from memory.short_term_memory import memory_manager

logger = logging.getLogger("AudioProcessor")

CANDIDATE_AUDIO_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash"
]

VOICE_REPLY_TRIGGERS = [
    "voice message", "voice note", "audio message", "audio note", "parayumo", "parayuu",
    "ayakkumo", "send voice", "voice il", "voice aayitt", "voiceil", "speak to me", "voice reply"
]

UNIFIED_AUDIO_PROMPT = """
You are the voice listener and support assistant for Juvelle, a premium women's Churidar tops boutique in Kerala.
Listen to this customer voice note audio carefully.

DOMAIN KNOWLEDGE & PHONETIC HINTS:
- Products: Exclusively daily wear and office wear Churidar tops / kurtis (sizes XS to 4XL, prices ₹499 to ₹1,299).
- We do NOT sell full sets, churidar bottoms, dupattas, or men's/kids wear.
- Shipping & COD: Pan-India delivery available, Cash on Delivery (COD) supported across Kerala and major cities.
- Store: Online store based in Kochi, Kerala.
- Spoken Language: English, Malayalam, or colloquial Manglish (Malayalam written in English script).
- Common phonetic terms: 'churidhar undo', 'kurti', 'ethraya', 'rate', 'price', 'kanikku', 'parayuu', 'daily wear', 'office wear', 'cash on delivery', 'cod', 'size', 'colour', 'stock'.

INSTRUCTIONS:
1. Accurately transcribe the spoken words. If spoken in Manglish, write natural Manglish. If spoken in English, write in English. If Malayalam, write in Malayalam script.
2. Identify the language: 'english', 'manglish', or 'malayalam_script'.
3. Formulate a warm, professional, concise Juvelle support reply (1-3 sentences) strictly in the detected language.

OUTPUT FORMAT (Strictly format as):
TRANSCRIPT: <transcribed text>
LANGUAGE: <english|manglish|malayalam_script>
REPLY: <juvelle customer support reply>
"""

def check_voice_reply_requested(text: str) -> bool:
    """Checks if the user explicitly asked for a voice message / audio note response."""
    if not text:
        return False
    text_lower = text.lower()
    return any(trigger in text_lower for trigger in VOICE_REPLY_TRIGGERS)

def generate_tts_base64(text: str, language: str = "english") -> Optional[str]:
    """Generates an MP3 audio voice note using gTTS and returns base64 data URI."""
    try:
        clean_text = re.sub(r'[*#_`~]', '', text).strip()
        if not clean_text:
            return None

        lang_code = 'en'
        tld = 'co.in'
        if language == "malayalam_script":
            lang_code = 'ml'
            tld = 'com'

        tts = gTTS(text=clean_text, lang=lang_code, tld=tld, slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        audio_b64 = base64.b64encode(fp.read()).decode('utf-8')
        return f"data:audio/mp3;base64,{audio_b64}"
    except Exception as e:
        logger.error(f"TTS generation error: {e}")
        return None

def transcribe_audio_with_gemini(audio_bytes: bytes, mime_type: str = "audio/webm") -> Dict[str, str]:
    """
    Directly transcribes customer voice note using Gemini Multimodal Audio reasoning.
    Accurately recognizes English, Malayalam script, and colloquial Manglish.
    """
    client = get_genai_client()
    if not client:
        return {
            "transcript": "Audio message received",
            "detected_language": "english"
        }

    transcription_prompt = """
You are the voice listener for Juvelle Boutique customer support in Kerala.
Listen to this customer voice note carefully and perform 2 tasks:
1. Transcribe the spoken words EXACTLY as spoken. If spoken in Manglish (Malayalam words written in English letters like 'churidhar undo', 'price ethraya'), write the transcript in natural Manglish. If spoken in English, write in English. If spoken in Malayalam, write in Malayalam script.
2. Identify the language ('english', 'manglish', or 'malayalam_script').

Domain Vocabulary: Churidar tops, kurtis, daily wear, office wear, size XS to 4XL, cotton, rayon, silk, ₹499 to ₹1299, cash on delivery, ethraya, undo, kanikku, parayuu.

Format your response strictly as:
TRANSCRIPT: <exact transcribed text>
LANGUAGE: <english|manglish|malayalam_script>
"""

    for model_name in CANDIDATE_AUDIO_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    transcription_prompt
                ]
            )
            raw_text = response.text.strip() if response.text else ""
            
            transcript = "Audio message received"
            lang = "english"
            
            if "TRANSCRIPT:" in raw_text:
                parts = raw_text.split("TRANSCRIPT:", 1)[1]
                if "LANGUAGE:" in parts:
                    t_part, l_part = parts.split("LANGUAGE:", 1)
                    transcript = t_part.strip()
                    lang_candidate = l_part.strip().lower()
                    if lang_candidate in ["english", "manglish", "malayalam_script"]:
                        lang = lang_candidate
                else:
                    transcript = parts.strip()
            elif raw_text:
                transcript = raw_text

            return {
                "transcript": transcript,
                "detected_language": lang
            }
        except Exception as e:
            logger.warning(f"Audio transcription model '{model_name}' failed: {e}")
            continue

    return {
        "transcript": "Audio message received",
        "detected_language": "english"
    }

def process_voice_message(
    audio_bytes: bytes,
    mime_type: str = "audio/webm",
    session_id: str = "default_user",
    customer_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    High-speed, accurate unified voice message pipeline:
    1. Attempts fast single-pass multimodal audio reasoning with Gemini 2.0 Flash (~1.1s latency).
    2. Falls back to 2-stage grounded RAG pipeline if needed.
    3. Conditionally generates TTS voice reply if customer requested audio.
    """
    logger.info(f"Processing incoming voice message ({len(audio_bytes)} bytes, mime: {mime_type}) for session: {session_id}")
    client = get_genai_client()

    transcript = None
    detected_lang = "english"
    reply_text = None

    # Step 1: Attempt ultra-fast single-pass audio reasoning
    if client:
        for model_name in CANDIDATE_AUDIO_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                        UNIFIED_AUDIO_PROMPT
                    ]
                )
                raw_text = response.text.strip() if response.text else ""
                
                if "TRANSCRIPT:" in raw_text and "REPLY:" in raw_text:
                    t_section = raw_text.split("TRANSCRIPT:", 1)[1]
                    if "LANGUAGE:" in t_section:
                        t_val, rem = t_section.split("LANGUAGE:", 1)
                        l_val, r_val = rem.split("REPLY:", 1)
                        transcript = t_val.strip()
                        detected_lang = l_val.strip().lower()
                        reply_text = r_val.strip()
                    else:
                        t_val, r_val = t_section.split("REPLY:", 1)
                        transcript = t_val.strip()
                        reply_text = r_val.strip()
                    
                    if detected_lang not in ["english", "manglish", "malayalam_script"]:
                        detected_lang = "english"

                    logger.info(f"Single-pass audio success via {model_name}: '{transcript}' -> '{reply_text[:60]}...'")
                    break
            except Exception as ex:
                logger.warning(f"Single-pass audio model '{model_name}' notice: {ex}")
                continue

    # Step 2: Fallback to 2-stage RAG if single-pass was not completed
    if not transcript or not reply_text:
        transcription_result = transcribe_audio_with_gemini(audio_bytes, mime_type=mime_type)
        transcript = transcription_result["transcript"]
        detected_lang = transcription_result["detected_language"]

        reply_text = generate_juvelle_reply(
            customer_message=transcript,
            session_id=session_id,
            customer_name=customer_name
        )

    # Step 3: Record conversation turns into memory
    try:
        memory_manager.add_message(session_id, "user", f"[Voice Note]: {transcript}")
        memory_manager.add_message(session_id, "assistant", reply_text)
    except Exception as mem_ex:
        logger.debug(f"Memory logging notice: {mem_ex}")

    # Step 4: Check if user requested a voice reply
    wants_voice = check_voice_reply_requested(transcript)
    audio_data = None
    if wants_voice:
        audio_data = generate_tts_base64(reply_text, language=detected_lang)
        logger.info("Generated TTS audio voice response for user request.")

    return {
        "transcript": transcript,
        "detected_language": detected_lang,
        "reply_text": reply_text,
        "audio_data": audio_data,
        "has_audio_reply": bool(audio_data),
        "session_id": session_id
    }
