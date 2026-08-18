import asyncio
import logging
import os
import urllib.request
import json
import time
from core.juvelle_agent import generate_juvelle_reply
from core.audio_processor import download_audio_bytes, transcribe_and_understand_voice_note
from mcp_server.meta_client import send_meta_graph_reply, _get_token

logger = logging.getLogger("LiveThreadWorker")

_PROCESSED_MESSAGE_IDS = set()
_RUNNING = False

async def live_instagram_poll_worker(poll_interval: float = 0.5):
    """
    Ultra-Fast 24/7 autonomous background worker (500ms polling).
    Zero static answers. Pure Gemini AI dynamic reasoning.
    Handles text DMs, Voice Notes, and Audio Attachments on Instagram.
    Transcribes audio using Gemini Multimodal LLM and dispatches instant brand replies.
    """
    global _PROCESSED_MESSAGE_IDS, _RUNNING
    if _RUNNING:
        return
    _RUNNING = True
    
    logger.info(f"Starting Ultra-Fast Autonomous Live Instagram DM Poller (Interval: {poll_interval*1000:.0f}ms)...")
    await asyncio.sleep(1)
    
    page_id = os.getenv("META_PAGE_ID", "932916046574692")
    default_thread_id = os.getenv("META_THREAD_ID", "aWdfZAG06MTpJR01lc3NhZA2VUaHJlYWQ6MTc4NDE0ODAxMDY5NzcxODI6MzQwMjgyMzY2ODQxNzEwMzAxMjQ0Mjc2MjY2MDMyODE4MTU5MDY1")
    
    while True:
        try:
            token = _get_token()
            if not token:
                await asyncio.sleep(poll_interval)
                continue
                
            # 1. Fetch active direct conversations
            conv_url = f"https://graph.facebook.com/v21.0/{page_id}/conversations?platform=instagram&access_token={token}"
            
            def _fetch_convs():
                req = urllib.request.Request(conv_url, headers={"User-Agent": "JuvelleBot/2.2"})
                with urllib.request.urlopen(req, timeout=6) as r:
                    return json.loads(r.read().decode("utf-8"))
                    
            conv_data = await asyncio.to_thread(_fetch_convs)
            conv_list = conv_data.get("data", [])
            thread_ids = [c["id"] for c in conv_list] if conv_list else [default_thread_id]
            
            for t_id in thread_ids:
                msg_url = f"https://graph.facebook.com/v21.0/{t_id}?fields=messages{{id,message,from,to,created_time,attachments,shares}}&limit=3&access_token={token}"
                
                def _fetch_msgs():
                    req = urllib.request.Request(msg_url, headers={"User-Agent": "JuvelleBot/2.2"})
                    with urllib.request.urlopen(req, timeout=6) as r:
                        return json.loads(r.read().decode("utf-8"))
                        
                msg_data = await asyncio.to_thread(_fetch_msgs)
                msgs = msg_data.get("messages", {}).get("data", [])
                
                if msgs:
                    latest = msgs[0]
                    msg_id = latest.get("id")
                    sender_username = latest.get("from", {}).get("username")
                    sender_id = latest.get("from", {}).get("id")
                    text = latest.get("message", "")
                    attachments = latest.get("attachments", {}).get("data", [])
                    
                    if msg_id and msg_id not in _PROCESSED_MESSAGE_IDS:
                        _PROCESSED_MESSAGE_IDS.add(msg_id)
                        
                        if sender_username != "juvelle.store":
                            t_start = time.time()
                            
                            # Check if audio attachment exists
                            is_audio = False
                            audio_url = None
                            for att in attachments:
                                att_type = att.get("type", "").lower()
                                if att_type in ["audio", "voice", "video"]:
                                    is_audio = True
                                    audio_url = att.get("payload", {}).get("url") or att.get("file_url")
                                    break
                                    
                            if is_audio and audio_url:
                                logger.info(f"[AUTONOMOUS BOT] Detected Audio Attachment from @{sender_username}. Downloading...")
                                audio_res = await asyncio.to_thread(download_audio_bytes, audio_url)
                                if audio_res:
                                    audio_bytes, mime = audio_res
                                    logger.info(f"[AUTONOMOUS BOT] Decoding audio ({mime}, {len(audio_bytes)} bytes) with Gemini 2.0 Flash...")
                                    text = await asyncio.to_thread(transcribe_and_understand_voice_note, audio_bytes, mime)
                                    logger.info(f"[AUTONOMOUS BOT] Transcribed voice message: '{text}'")
                            elif not text and text == "":
                                logger.info(f"[AUTONOMOUS BOT] Detected Voice Note event from @{sender_username} ({sender_id}). Generating dynamic AI context response...")
                                text = "Customer sent an Instagram voice message inquiry."
                                
                            if text:
                                logger.info(f"[AUTONOMOUS BOT] Running Gemini AI dynamic reasoning for @{sender_username}: '{text}'")
                                
                                # Pure Dynamic AI response from Gemini Spark Agent + Qdrant RAG + Session Memory
                                reply = generate_juvelle_reply(
                                    customer_message=text,
                                    session_id=sender_id or "customer_01",
                                    customer_name=sender_username or "Customer"
                                )
                                
                                # Dispatch reply to Instagram DM
                                res = send_meta_graph_reply(
                                    recipient_id=sender_id or "1701855650538450",
                                    message_text=reply
                                )
                                t_total = time.time() - t_start
                                logger.info(f"[AUTONOMOUS BOT] Auto-reply dispatched in {t_total:.2f}s | Status: {res.get('status')}")
                                
        except Exception as e:
            logger.debug(f"[AUTONOMOUS BOT] Poller notice: {e}")
            
        await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    print("Starting Ultra-Fast Autonomous Live Thread Worker (500ms polling + Gemini Multimodal Voice perception)...")
    asyncio.run(live_instagram_poll_worker(poll_interval=0.5))
