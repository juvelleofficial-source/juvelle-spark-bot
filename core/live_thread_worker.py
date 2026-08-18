import asyncio
import logging
import os
import urllib.request
import json
from core.juvelle_agent import generate_juvelle_reply
from mcp_server.meta_client import send_meta_graph_reply, _get_token

logger = logging.getLogger("LiveThreadWorker")

_LAST_PROCESSED_MESSAGE_ID = None
_RUNNING = False

async def live_instagram_poll_worker(poll_interval: int = 4):
    """
    Continuous 24/7 background worker that polls Meta Graph API for active
    Instagram conversation threads and automatically generates brand AI replies.
    Guarantees instant response delivery even when Meta Webhooks are restricted or delayed.
    """
    global _LAST_PROCESSED_MESSAGE_ID, _RUNNING
    if _RUNNING:
        return
    _RUNNING = True
    
    logger.info("Starting 24/7 Real-Time Live Instagram DM Poller Worker...")
    
    # Wait for server startup
    await asyncio.sleep(5)
    
    thread_id = os.getenv("META_THREAD_ID", "aWdfZAG06MTpJR01lc3NhZA2VUaHJlYWQ6MTc4NDE0ODAxMDY5NzcxODI6MzQwMjgyMzY2ODQxNzEwMzAxMjQ0Mjc2MjY2MDMyODE4MTU5MDY1")
    page_id = os.getenv("META_PAGE_ID", "932916046574692")
    
    while True:
        try:
            token = _get_token()
            if not token:
                await asyncio.sleep(poll_interval)
                continue
                
            # Query the latest message in the direct thread
            url = f"https://graph.facebook.com/v21.0/{thread_id}?fields=messages{{id,message,from,to,created_time}}&limit=3&access_token={token}"
            
            def _fetch():
                req = urllib.request.Request(url, headers={"User-Agent": "JuvelleBot/2.2"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    return json.loads(r.read().decode("utf-8"))
                    
            data = await asyncio.to_thread(_fetch)
            msgs = data.get("messages", {}).get("data", [])
            
            if msgs:
                latest = msgs[0]
                msg_id = latest.get("id")
                sender_username = latest.get("from", {}).get("username")
                sender_id = latest.get("from", {}).get("id")
                text = latest.get("message", "")
                
                # If new message from a customer and not from the bot itself
                if msg_id != _LAST_PROCESSED_MESSAGE_ID and sender_username != "juvelle.store" and text:
                    _LAST_PROCESSED_MESSAGE_ID = msg_id
                    logger.info(f"[LIVE POLLER] Detected new DM from {sender_username} ({sender_id}): '{text}'")
                    
                    # Generate AI response
                    reply = generate_juvelle_reply(
                        customer_message=text,
                        session_id=sender_id or "customer_01",
                        customer_name=sender_username or "Customer"
                    )
                    logger.info(f"[LIVE POLLER] Generated AI response: '{reply}'")
                    
                    # Dispatch to customer via Meta Graph API
                    res = send_meta_graph_reply(recipient_id=sender_id or "1701855650538450", message_text=reply)
                    logger.info(f"[LIVE POLLER] Dispatched reply: {res.get('status')}")
                    
        except Exception as e:
            logger.debug(f"[LIVE POLLER] Polling notice: {e}")
            
        await asyncio.sleep(poll_interval)
