import json
import logging
import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Response, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse, PlainTextResponse, HTMLResponse
from sse_starlette.sse import EventSourceResponse

from mcp_server.tools_registry import MCP_TOOLS_MANIFEST, execute_mcp_tool
from mcp_server.message_queue import (
    enqueue_facebook_message,
    mark_message_replied,
    is_meta_mid_processed,
    mark_meta_mid_processed
)
from mcp_server.meta_client import META_VERIFY_TOKEN, send_meta_graph_reply, send_meta_sender_action
from core.audio_processor import download_audio_bytes, transcribe_and_understand_voice_note

logger = logging.getLogger(__name__)

mcp_router = APIRouter(prefix="", tags=["Gemini Spark MCP & Meta Webhooks"])



# ==============================================================================
# 1. MODEL CONTEXT PROTOCOL (MCP) ENDPOINTS FOR GEMINI SPARK
# ==============================================================================

@mcp_router.api_route("/mcp/sse", methods=["GET", "HEAD", "OPTIONS"])
async def mcp_sse_stream(request: Request):
    """
    Standard Server-Sent Events (SSE) endpoint for Gemini Spark to establish
    an active connection with this custom MCP server.
    Supports GET, HEAD, and OPTIONS for validation probes.
    """
    if request.method == "HEAD":
        return Response(status_code=200, media_type="text/event-stream")
    
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            }
        )

    session_id = request.query_params.get("sessionId") or f"spark_{uuid.uuid4().hex[:8]}"
    base_url = str(request.base_url).rstrip("/")
    messages_endpoint = f"{base_url}/mcp/messages"

    async def event_publisher():
        # Register this Spark session for real-time push notifications
        push_queue = _register_sse_session(session_id)
        
        try:
            # Emit initial endpoint discovery event according to MCP SSE specification
            yield {
                "event": "endpoint",
                "data": f"/mcp/messages?sessionId={session_id}"
            }
            # Combined heartbeat + push notification loop
            while True:
                if await request.is_disconnected():
                    break
                # Check for push notifications (new_message events) with 15s timeout for heartbeat
                try:
                    import asyncio
                    event = await asyncio.wait_for(push_queue.get(), timeout=15.0)
                    yield event
                except asyncio.TimeoutError:
                    # No push events — send heartbeat
                    yield {
                        "event": "ping",
                        "data": json.dumps({"status": "active"})
                    }
        finally:
            _unregister_sse_session(session_id)

    return EventSourceResponse(
        event_publisher(),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )

@mcp_router.api_route("/mcp/messages", methods=["POST", "OPTIONS"])
@mcp_router.post("/mcp/sse")
async def handle_mcp_jsonrpc(request: Request):
    """
    Standard JSON-RPC 2.0 message handler for Gemini Spark.
    Handles 'initialize', 'tools/list', 'tools/call', and 'ping'.
    Also bound to POST /mcp/sse for clients using Streamable HTTP transport.
    """
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            }
        )

    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    msg_id = body.get("id", "1")
    method = body.get("method", "")
    params = body.get("params", {})

    logger.info(f"Received MCP JSON-RPC Method: '{method}' (id: {msg_id})")

    # 1. Handle Initialization Handshake
    if method == "initialize":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {
                            "listChanged": False
                        }
                    },
                    "serverInfo": {
                        "name": "Gemini-Spark-Facebook-MCP-Server",
                        "version": "1.0.0"
                    }
                }
            },
            headers={"Access-Control-Allow-Origin": "*"}
        )

    # 2. Handle Tools Manifest Listing
    elif method == "tools/list":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": MCP_TOOLS_MANIFEST
                }
            },
            headers={"Access-Control-Allow-Origin": "*"}
        )

    # 3. Handle Tool Execution
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        
        try:
            tool_output = execute_mcp_tool(tool_name, arguments)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(tool_output, indent=2)
                            }
                        ],
                        "isError": "error" in tool_output
                    }
                },
                headers={"Access-Control-Allow-Origin": "*"}
            )
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}")
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32000,
                        "message": str(e)
                    }
                },
                headers={"Access-Control-Allow-Origin": "*"}
            )

    # 4. Handle Ping / Notifications
    elif method == "ping" or method == "notifications/initialized":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {}
            },
            headers={"Access-Control-Allow-Origin": "*"}
        )

    else:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            },
            headers={"Access-Control-Allow-Origin": "*"}
        )

# ==============================================================================
# 2. OAUTH & WELL-KNOWN MCP DISCOVERY PROBES
# ==============================================================================

@mcp_router.get("/.well-known/oauth-protected-resource")
@mcp_router.get("/.well-known/oauth-protected-resource/mcp/sse")
@mcp_router.get("/.well-known/oauth-authorization-server")
def oauth_protected_resource():
    """Returns empty public OAuth metadata indicating server is public / unauthenticated."""
    return JSONResponse(
        {
            "resource": "https://study-breeding-structure-download.trycloudflare.com",
            "authorization_servers": []
        },
        headers={"Access-Control-Allow-Origin": "*"}
    )

@mcp_router.get("/privacy", response_class=HTMLResponse)
def privacy_policy():
    """Public Privacy Policy required by Meta Developer Console for Live Production mode."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Privacy Policy - Juvelle</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #1e293b; }
            h1 { color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }
            h2 { color: #334155; margin-top: 24px; }
        </style>
    </head>
    <body>
        <h1>Privacy Policy for Juvelle Store AI Assistant</h1>
        <p><strong>Effective Date:</strong> August 19, 2026</p>
        <p>Juvelle ("we", "our", or "us") provides conversational customer support via Instagram and Facebook Messenger through our automated AI assistant.</p>
        
        <h2>1. Information We Collect</h2>
        <p>We only collect and process incoming customer messages, Instagram user identifiers (scoped IDs), and conversation timestamps necessary to understand and answer your inquiries regarding our women's Churidar tops and apparel collections.</p>
        
        <h2>2. How We Use Your Information</h2>
        <p>Your messages are used strictly in real-time to generate helpful, accurate product recommendations, catalog queries, and customer service answers. We do not sell or rent personal data to third parties.</p>
        
        <h2>3. Data Retention & Security</h2>
        <p>Conversation logs and memory are maintained securely to provide consistent customer support. You may request data deletion at any time by contacting our support team at <em>support@juvelle.store</em>.</p>
        
        <h2>4. Contact Us</h2>
        <p>If you have any questions regarding this Privacy Policy, please reach out to us at <em>support@juvelle.store</em>.</p>
    </body>
    </html>
    """

@mcp_router.get("/terms", response_class=HTMLResponse)
def terms_of_service():
    """Public Terms of Service required by Meta Developer Console for Live Production mode."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Terms of Service - Juvelle</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #1e293b; }
            h1 { color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }
        </style>
    </head>
    <body>
        <h1>Terms of Service for Juvelle Store Assistant</h1>
        <p><strong>Effective Date:</strong> August 19, 2026</p>
        <p>By interacting with Juvelle's automated customer service assistants on Meta platforms (Instagram, Facebook), you agree to these Terms.</p>
        <p>Our assistant provides product recommendations, sizing advice, and catalog information for our women's Churidar collection. Product availability and pricing are subject to final confirmation on our official store.</p>
    </body>
    </html>
    """

# ==============================================================================
# 3. FACEBOOK DEVELOPER (META GRAPH API) WEBHOOK ENDPOINTS
# ==============================================================================

@mcp_router.get("/webhook/facebook")
@mcp_router.get("/webhook/instagram")
@mcp_router.get("/webhook/meta")
def verify_facebook_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge")
):
    """
    Verification endpoint for Facebook Developer / Meta Webhooks (Instagram & Messenger).
    Meta sends a GET request with hub.mode=subscribe, hub.verify_token, and hub.challenge.
    Returns raw hub.challenge as text/plain to complete the verification handshake.
    """
    logger.info(f"Meta/Instagram Webhook Verification Probe: mode={hub_mode}, token={hub_verify_token}")
    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        logger.info("Meta/Instagram Webhook handshake verified successfully!")
        return PlainTextResponse(content=hub_challenge or "")
    
    logger.warning(f"Meta Webhook Token mismatch: expected '{META_VERIFY_TOKEN}', got '{hub_verify_token}'")
    raise HTTPException(status_code=403, detail="Verification token mismatch")

# ==============================================================================
# REAL-TIME SSE PUSH NOTIFICATION SYSTEM FOR GEMINI SPARK
# ==============================================================================
# The MCP server does NOT generate AI replies. Gemini Spark (24/7 cloud agent)
# handles all reasoning and reply generation via MCP tools.
# When a new DM arrives, we push an SSE event to all connected Spark sessions.

import asyncio as _sse_asyncio

_ACTIVE_SSE_SESSIONS: dict = {}  # session_id -> asyncio.Queue

def _register_sse_session(session_id: str) -> _sse_asyncio.Queue:
    """Registers a Spark SSE session for real-time push notifications."""
    q = _sse_asyncio.Queue()
    _ACTIVE_SSE_SESSIONS[session_id] = q
    logger.info(f"Registered SSE session: {session_id} (total active: {len(_ACTIVE_SSE_SESSIONS)})")
    return q

def _unregister_sse_session(session_id: str):
    """Removes a disconnected Spark SSE session."""
    _ACTIVE_SSE_SESSIONS.pop(session_id, None)
    logger.info(f"Unregistered SSE session: {session_id} (total active: {len(_ACTIVE_SSE_SESSIONS)})")

async def _broadcast_new_message(sender_id: str, message_text: str, platform: str):
    """Pushes a real-time 'new_message' event to all connected Gemini Spark sessions."""
    event_data = json.dumps({
        "type": "new_message",
        "sender_id": sender_id,
        "text": message_text[:200],
        "platform": platform
    })
    dead_sessions = []
    for sid, q in _ACTIVE_SSE_SESSIONS.items():
        try:
            await q.put({"event": "new_message", "data": event_data})
        except Exception:
            dead_sessions.append(sid)
    for sid in dead_sessions:
        _unregister_sse_session(sid)
    logger.info(f"Broadcast new_message to {len(_ACTIVE_SSE_SESSIONS)} Spark sessions for sender {sender_id}")

async def process_and_reply_async(
    sender_id: str,
    message_text: str,
    platform: str = "instagram",
    audio_url: Optional[str] = None,
    msg_id: Optional[str] = None
):
    """
    Autonomous background worker that generates a brand-grounded AI reply
    using the Juvelle conversational AI engine and dispatches it immediately via Meta Graph API.
    Emits real-time typing indicators and mark_seen actions for a native human feel.
    Handles both text DMs and audio voice notes.
    """
    try:
        from core.juvelle_agent import generate_juvelle_reply
        from core.audio_processor import download_audio_bytes, transcribe_and_understand_voice_note
        from mcp_server.message_queue import mark_message_replied

        logger.info(f"[AUTONOMOUS AI WORKER] Processing {platform} message from {sender_id} (Audio: {bool(audio_url)}): '{message_text}'")

        # 1. Immediate typing indicator acknowledgement
        try:
            send_meta_sender_action(recipient_id=sender_id, action="mark_seen")
            send_meta_sender_action(recipient_id=sender_id, action="typing_on")
        except Exception as e_action:
            logger.debug(f"Typing indicator notice: {e_action}")

        # 2. If voice note audio_url is present, transcribe it
        customer_query = message_text
        if audio_url:
            logger.info(f"[AUTONOMOUS AI WORKER] Downloading voice note for transcription: {audio_url}")
            audio_res = download_audio_bytes(audio_url)
            if audio_res:
                audio_bytes, mime = audio_res
                transcript = transcribe_and_understand_voice_note(audio_bytes, mime)
                if transcript:
                    logger.info(f"[AUTONOMOUS AI WORKER] Voice note transcribed: '{transcript}'")
                    customer_query = transcript
                else:
                    customer_query = "Customer sent a voice note inquiring about Juvelle daily and office wear churidar tops."
            else:
                customer_query = "Customer sent a voice note inquiring about Juvelle daily and office wear churidar tops."

        # 3. Generate grounded AI response
        reply_text = generate_juvelle_reply(
            customer_message=customer_query,
            session_id=sender_id,
            customer_name=sender_id,
            is_voice=bool(audio_url)
        )
        logger.info(f"[AUTONOMOUS AI WORKER] Generated AI reply for {sender_id}: '{reply_text}'")

        # 4. Dispatch response via Meta Graph API
        result = send_meta_graph_reply(recipient_id=sender_id, message_text=reply_text)
        logger.info(f"[AUTONOMOUS AI WORKER] Meta Graph API dispatch result for {sender_id}: {result}")

        # 5. Mark as replied in queue
        if msg_id:
            mark_message_replied(message_id=msg_id, ai_reply=reply_text)

    except Exception as e:
        logger.error(f"[AUTONOMOUS AI WORKER] Error processing auto-reply for {sender_id}: {e}", exc_info=True)

# Ring buffer for live webhook telemetry (in-memory + diagnostic)
WEBHOOK_LOGS = []

@mcp_router.get("/webhook_logs")
def get_webhook_logs(limit: int = 50):
    """Returns recent raw Meta Webhook incoming events for debugging."""
    return JSONResponse({
        "total_events": len(WEBHOOK_LOGS),
        "events": WEBHOOK_LOGS[-limit:][::-1]
    })

@mcp_router.get("/webhook_logs/html", response_class=HTMLResponse)
def get_webhook_logs_html():
    """Visual real-time dashboard for inspecting incoming Meta Webhook events."""
    import html
    rows = ""
    for ev in WEBHOOK_LOGS[::-1]:
        ts = html.escape(str(ev.get("timestamp", "")))
        obj = html.escape(str(ev.get("object", "")))
        sender = html.escape(str(ev.get("sender_id", "N/A")))
        text = html.escape(str(ev.get("text", "N/A")))
        status = html.escape(str(ev.get("status", "")))
        raw = html.escape(json.dumps(ev.get("raw_data", {}), indent=2))
        rows += f"""
        <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 10px; font-family: monospace; font-size: 12px;">{ts}</td>
            <td style="padding: 10px; font-weight: bold; color: #3b82f6;">{obj}</td>
            <td style="padding: 10px; font-family: monospace;">{sender}</td>
            <td style="padding: 10px;">{text}</td>
            <td style="padding: 10px;"><span style="background: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 4px; font-size: 11px;">{status}</span></td>
            <td style="padding: 10px;"><details><summary style="cursor: pointer; color: #64748b; font-size: 12px;">View Payload</summary><pre style="background: #f1f5f9; padding: 8px; font-size: 11px; border-radius: 4px; max-height: 150px; overflow: auto;">{raw}</pre></details></td>
        </tr>
        """
    if not rows:
        rows = '<tr><td colspan="6" style="padding: 20px; text-align: center; color: #94a3b8;">No incoming webhook events recorded yet. Send a DM to trigger an event!</td></tr>'

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="refresh" content="5">
        <title>Juvelle Bot - Live Webhook Telemetry</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 24px; }}
            .card {{ background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; overflow: hidden; }}
            table {{ width: 100%; border-collapse: collapse; text-align: left; }}
            th {{ background: #f1f5f9; padding: 12px 10px; font-size: 12px; text-transform: uppercase; color: #475569; }}
        </style>
    </head>
    <body>
        <div style="max-width: 1200px; margin: 0 auto;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h1 style="margin: 0; font-size: 20px;">⚡ Juvelle Bot - Live Meta Webhook Monitor</h1>
                <span style="font-size: 12px; color: #64748b;">Auto-refreshing every 5s | Total Events: {len(WEBHOOK_LOGS)}</span>
            </div>
            <div class="card">
                <table>
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>Object</th>
                            <th>Sender ID</th>
                            <th>Message Text</th>
                            <th>Status</th>
                            <th>Raw Payload</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """


@mcp_router.post("/webhook/facebook")
@mcp_router.post("/webhook/instagram")
@mcp_router.post("/webhook/meta")
async def receive_facebook_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives incoming messaging events from Facebook Messenger, WhatsApp, or Instagram DMs.
    Enqueues messages into SQLite inbox, broadcasts real-time SSE notifications to Gemini Spark,
    and runs the autonomous background AI reply worker to respond via Meta Graph API.
    """
    import datetime
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"status": "invalid_json"}, status_code=400)

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    logger.info(f"Incoming Meta Webhook event: {json.dumps(data)}")

    event_object = data.get("object", "unknown")
    event_entry = {
        "timestamp": now_iso,
        "object": event_object,
        "raw_data": data,
        "status": "RECEIVED"
    }

    # Parse standard Meta Instagram & Messenger event payload
    if event_object in ["page", "instagram"]:
        platform_name = "instagram" if event_object == "instagram" else "messenger"
        for entry in data.get("entry", []):
            # 1. Check messaging array (standard Meta Messenger/Instagram format)
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                message = messaging_event.get("message", {})
                text = message.get("text")
                mid = message.get("mid")
                attachments = message.get("attachments", [])

                # Skip echo messages sent by the bot/page itself
                if message.get("is_echo"):
                    logger.info(f"Skipping echo message for {sender_id}")
                    continue

                if mid and is_meta_mid_processed(mid):
                    logger.info(f"Skipping duplicate messaging event for MID: {mid}")
                    continue

                # Voice Note / Audio Attachment Detection (100% Free Gemini Spark MCP pipeline)
                audio_link = None
                if attachments:
                    for att in attachments:
                        att_type = att.get("type", "").lower()
                        if "audio" in att_type or "voice" in att_type or "video" in att_type:
                            audio_link = att.get("payload", {}).get("url") or att.get("file_url")
                            break

                if not text and audio_link:
                    text = "[Voice Message Attached - Listen to audio_url]"

                if sender_id and (text or audio_link):
                    if mid:
                        mark_meta_mid_processed(mid)
                    event_entry["sender_id"] = sender_id
                    event_entry["text"] = text or "[Voice Message]"
                    event_entry["status"] = "QUEUED_FOR_SPARK"
                    msg_id = enqueue_facebook_message(
                        sender_id=sender_id,
                        message_text=text or "[Voice Message]",
                        platform=platform_name,
                        meta_mid=mid,
                        audio_url=audio_link
                    )
                    logger.info(f"Enqueued {platform_name} message from {sender_id} (MID: {mid}, Audio: {bool(audio_link)}): '{text}'")
                    await _broadcast_new_message(sender_id, text or "[Voice Message]", platform_name)
                    # Trigger autonomous AI worker to reply immediately
                    background_tasks.add_task(
                        process_and_reply_async,
                        sender_id,
                        text or "[Voice Message]",
                        platform_name,
                        audio_link,
                        msg_id
                    )

            # 2. Check standby array
            for standby_event in entry.get("standby", []):
                sender_id = standby_event.get("sender", {}).get("id")
                message = standby_event.get("message", {})
                text = message.get("text")
                mid = message.get("mid")

                if mid and is_meta_mid_processed(mid):
                    logger.info(f"Skipping duplicate standby event for MID: {mid}")
                    continue

                if sender_id and text:
                    if mid:
                        mark_meta_mid_processed(mid)
                    event_entry["sender_id"] = sender_id
                    event_entry["text"] = text
                    event_entry["status"] = "STANDBY_QUEUED"
                    msg_id = enqueue_facebook_message(
                        sender_id=sender_id,
                        message_text=text,
                        platform=platform_name,
                        meta_mid=mid
                    )
                    await _broadcast_new_message(sender_id, text, platform_name)
                    background_tasks.add_task(
                        process_and_reply_async,
                        sender_id,
                        text,
                        platform_name,
                        None,
                        msg_id
                    )

            # 3. Check changes array (alternative Instagram Graph Webhooks format)
            for change in entry.get("changes", []):
                field = change.get("field")
                value = change.get("value", {})
                if field in ["messages", "messaging_postbacks"] or "messages" in change:
                    sender_id = value.get("sender", {}).get("id") or value.get("from", {}).get("id") or value.get("from")
                    message_obj = value.get("message", {})
                    text = message_obj.get("text") or value.get("text") or (value.get("messages", [{}])[0].get("text", {}).get("body") if isinstance(value.get("messages"), list) and value.get("messages") else None)
                    mid = message_obj.get("mid") or value.get("mid")

                    if mid and is_meta_mid_processed(mid):
                        logger.info(f"Skipping duplicate changes event for MID: {mid}")
                        continue

                    if sender_id and text:
                        if mid:
                            mark_meta_mid_processed(mid)
                        event_entry["sender_id"] = str(sender_id)
                        event_entry["text"] = str(text)
                        event_entry["status"] = "CHANGES_QUEUED"
                        msg_id = enqueue_facebook_message(
                            sender_id=str(sender_id),
                            message_text=str(text),
                            platform=platform_name,
                            meta_mid=mid
                        )
                        logger.info(f"Enqueued {platform_name} message from changes ({sender_id}, MID: {mid}): '{text}'")
                        await _broadcast_new_message(str(sender_id), str(text), platform_name)
                        background_tasks.add_task(
                            process_and_reply_async,
                            str(sender_id),
                            str(text),
                            platform_name,
                            None,
                            msg_id
                        )

        WEBHOOK_LOGS.append(event_entry)
        if len(WEBHOOK_LOGS) > 100:
            WEBHOOK_LOGS.pop(0)

        return PlainTextResponse("EVENT_RECEIVED", status_code=200)

    elif event_object == "whatsapp_business_account":
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    from_number = message.get("from")
                    text = message.get("text", {}).get("body")
                    if from_number and text:
                        event_entry["sender_id"] = str(from_number)
                        event_entry["text"] = str(text)
                        event_entry["status"] = "WHATSAPP_QUEUED"
                        enqueue_facebook_message(
                            sender_id=str(from_number),
                            message_text=str(text),
                            platform="whatsapp"
                        )
                        logger.info(f"Enqueued whatsapp message from {from_number}: '{text}'")
                        await _broadcast_new_message(str(from_number), str(text), "whatsapp")

        WEBHOOK_LOGS.append(event_entry)
        if len(WEBHOOK_LOGS) > 100:
            WEBHOOK_LOGS.pop(0)

        return PlainTextResponse("EVENT_RECEIVED", status_code=200)

    WEBHOOK_LOGS.append(event_entry)
    if len(WEBHOOK_LOGS) > 100:
        WEBHOOK_LOGS.pop(0)

    return PlainTextResponse("EVENT_RECEIVED", status_code=200)


