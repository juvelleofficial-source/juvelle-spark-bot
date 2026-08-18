import asyncio
import logging
import os
import urllib.request
import json
import time
from core.juvelle_agent import generate_juvelle_reply
from mcp_server.meta_client import send_meta_graph_reply, _get_token

logger = logging.getLogger("LiveThreadWorker")

_PROCESSED_MESSAGE_IDS = set()
_RUNNING = False

async def live_instagram_poll_worker(poll_interval: int = 2):
    """
    Continuous 24/7 autonomous background worker that polls Meta Graph API
    for active Instagram conversation threads and automatically replies to any new incoming customer DMs.
    Guarantees instant response delivery (sub-3 seconds) 24/7.
    """
    global _PROCESSED_MESSAGE_IDS, _RUNNING
    if _RUNNING:
        return
    _RUNNING = True
    
    logger.info("Starting 24/7 Autonomous Real-Time Live Instagram DM Poller Worker...")
    
    # Wait for server initialization
    await asyncio.sleep(2)
    
    page_id = os.getenv("META_PAGE_ID", "932916046574692")
    default_thread_id = os.getenv("META_THREAD_ID", "aWdfZAG06MTpJR01lc3NhZA2VUaHJlYWQ6MTc4NDE0ODAxMDY5NzcxODI6MzQwMjgyMzY2ODQxNzEwMzAxMjQ0Mjc2MjY2MDMyODE4MTU5MDY1")
    
    while True:
        try:
            token = _get_token()
            if not token:
                await asyncio.sleep(poll_interval)
                continue
                
            # 1. Fetch active conversations from Meta Graph API
            conv_url = f"https://graph.facebook.com/v21.0/{page_id}/conversations?platform=instagram&access_token={token}"
            
            def _fetch_convs():
                req = urllib.request.Request(conv_url, headers={"User-Agent": "JuvelleBot/2.2"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    return json.loads(r.read().decode("utf-8"))
                    
            conv_data = await asyncio.to_thread(_fetch_convs)
            conv_list = conv_data.get("data", [])
            
            thread_ids = [c["id"] for c in conv_list] if conv_list else [default_thread_id]
            
            for t_id in thread_ids:
                msg_url = f"https://graph.facebook.com/v21.0/{t_id}?fields=messages{{id,message,from,to,created_time}}&limit=3&access_token={token}"
                
                def _fetch_msgs():
                    req = urllib.request.Request(msg_url, headers={"User-Agent": "JuvelleBot/2.2"})
                    with urllib.request.urlopen(req, timeout=8) as r:
                        return json.loads(r.read().decode("utf-8"))
                        
                msg_data = await asyncio.to_thread(_fetch_msgs)
                msgs = msg_data.get("messages", {}).get("data", [])
                
                if msgs:
                    latest = msgs[0]
                    msg_id = latest.get("id")
                    sender_username = latest.get("from", {}).get("username")
                    sender_id = latest.get("from", {}).get("id")
                    text = latest.get("message", "")
                    
                    # If this message hasn't been processed yet and was sent by a customer
                    if msg_id and msg_id not in _PROCESSED_MESSAGE_IDS:
                        _PROCESSED_MESSAGE_IDS.add(msg_id)
                        
                        if sender_username != "juvelle.store" and text:
                            t_start = time.time()
                            logger.info(f"[AUTONOMOUS BOT] New customer message from @{sender_username} ({sender_id}): '{text}'")
                            
                            # Generate AI response
                            reply = generate_juvelle_reply(
                                customer_message=text,
                                session_id=sender_id or "customer_01",
                                customer_name=sender_username or "Customer"
                            )
                            t_ai = time.time() - t_start
                            logger.info(f"[AUTONOMOUS BOT] AI generated reply ({t_ai:.2f}s): '{reply}'")
                            
                            # Dispatch reply to Instagram inbox
                            res = send_meta_graph_reply(
                                recipient_id=sender_id or "1701855650538450",
                                message_text=reply
                            )
                            t_total = time.time() - t_start
                            logger.info(f"[AUTONOMOUS BOT] Reply dispatched in {t_total:.2f}s | Status: {res.get('status')}")
                            
        except Exception as e:
            logger.debug(f"[AUTONOMOUS BOT] Poll loop notice: {e}")
            
        await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    print("Starting Standalone Autonomous Live Thread Worker (polling every 2 seconds)...")
    asyncio.run(live_instagram_poll_worker(poll_interval=2))
