import json
import logging
import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Response, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse, PlainTextResponse, HTMLResponse
from sse_starlette.sse import EventSourceResponse

from mcp_server.tools_registry import MCP_TOOLS_MANIFEST, execute_mcp_tool
from mcp_server.message_queue import enqueue_facebook_message
from mcp_server.meta_client import META_VERIFY_TOKEN, send_meta_graph_reply

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
        # Emit initial endpoint discovery event according to MCP SSE specification
        yield {
            "event": "endpoint",
            "data": f"/mcp/messages?sessionId={session_id}"
        }
        # Keep-alive heartbeat
        while True:
            if await request.is_disconnected():
                break
            import asyncio
            await asyncio.sleep(15)
            yield {
                "event": "ping",
                "data": json.dumps({"status": "active"})
            }

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

async def process_and_reply_async(sender_id: str, message_text: str, platform: str = "instagram"):
    """
    Autonomous background worker that generates a brand-grounded AI reply
    using Juvelle conversational AI engine and dispatches it immediately via Meta Graph API.
    """
    try:
        from core.juvelle_agent import generate_juvelle_reply
        logger.info(f"[AUTONOMOUS WORKER] Processing {platform} message from {sender_id}: '{message_text}'")
        reply_text = generate_juvelle_reply(
            customer_message=message_text,
            session_id=sender_id,
            customer_name=sender_id
        )
        logger.info(f"[AUTONOMOUS WORKER] Generated AI reply for {sender_id}: '{reply_text}'")
        
        result = send_meta_graph_reply(recipient_id=sender_id, message_text=reply_text)
        logger.info(f"[AUTONOMOUS WORKER] Meta Graph API dispatch result for {sender_id}: {result}")
    except Exception as e:
        logger.error(f"[AUTONOMOUS WORKER] Error processing auto-reply for {sender_id}: {e}", exc_info=True)


@mcp_router.post("/webhook/facebook")
@mcp_router.post("/webhook/instagram")
@mcp_router.post("/webhook/meta")
async def receive_facebook_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives incoming messaging events from Facebook Messenger, WhatsApp, or Instagram DMs.
    Enqueues messages for audit and triggers autonomous real-time AI reply worker.
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"status": "invalid_json"}, status_code=400)

    logger.info(f"Incoming Meta Webhook event: {json.dumps(data)[:200]}...")

    # Parse standard Meta Instagram & Messenger event payload
    event_object = data.get("object")
    if event_object in ["page", "instagram"]:
        platform_name = "instagram" if event_object == "instagram" else "messenger"
        for entry in data.get("entry", []):
            # 1. Check messaging array (standard Meta Messenger/Instagram format)
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                message = messaging_event.get("message", {})
                text = message.get("text")

                # Skip echo messages sent by the bot/page itself
                if message.get("is_echo"):
                    continue

                if sender_id and text:
                    enqueue_facebook_message(
                        sender_id=sender_id,
                        message_text=text,
                        platform=platform_name
                    )
                    logger.info(f"Enqueued {platform_name} message from {sender_id}: '{text}'")
                    background_tasks.add_task(process_and_reply_async, sender_id, text, platform_name)

            # 2. Check changes array (alternative Instagram Graph Webhooks format)
            for change in entry.get("changes", []):
                field = change.get("field")
                value = change.get("value", {})
                if field in ["messages", "messaging_postbacks"] or "messages" in change:
                    sender_id = value.get("sender", {}).get("id") or value.get("from", {}).get("id") or value.get("from")
                    text = value.get("message", {}).get("text") or value.get("text") or (value.get("messages", [{}])[0].get("text", {}).get("body") if isinstance(value.get("messages"), list) and value.get("messages") else None)
                    if sender_id and text:
                        enqueue_facebook_message(
                            sender_id=sender_id,
                            message_text=text,
                            platform=platform_name
                        )
                        logger.info(f"Enqueued {platform_name} message from changes ({sender_id}): '{text}'")
                        background_tasks.add_task(process_and_reply_async, sender_id, text, platform_name)

        return PlainTextResponse("EVENT_RECEIVED", status_code=200)

    elif event_object == "whatsapp_business_account":
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    from_number = message.get("from")
                    text = message.get("text", {}).get("body")
                    if from_number and text:
                        enqueue_facebook_message(
                            sender_id=from_number,
                            message_text=text,
                            platform="whatsapp"
                        )
                        logger.info(f"Enqueued whatsapp message from {from_number}: '{text}'")
                        background_tasks.add_task(process_and_reply_async, from_number, text, "whatsapp")

        return PlainTextResponse("EVENT_RECEIVED", status_code=200)

    return PlainTextResponse("EVENT_RECEIVED", status_code=200)

