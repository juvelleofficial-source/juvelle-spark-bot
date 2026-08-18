import json
import logging
import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Response, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse, PlainTextResponse, Response
from sse_starlette.sse import EventSourceResponse

from mcp_server.tools_registry import MCP_TOOLS_MANIFEST, execute_mcp_tool
from mcp_server.message_queue import enqueue_facebook_message
from mcp_server.meta_client import META_VERIFY_TOKEN

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

# ==============================================================================
# 3. FACEBOOK DEVELOPER (META GRAPH API) WEBHOOK ENDPOINTS
# ==============================================================================

@mcp_router.get("/webhook/facebook")
def verify_facebook_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge")
):
    """
    Verification endpoint for Facebook Developer / Meta Webhooks.
    Meta sends a GET request with hub.mode=subscribe and hub.verify_token.
    """
    logger.info(f"Facebook Webhook Verification: mode={hub_mode}, token={hub_verify_token}")
    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        logger.info("Facebook Webhook verified successfully!")
        return PlainTextResponse(content=hub_challenge or "")
    
    raise HTTPException(status_code=403, detail="Verification token mismatch")

@mcp_router.post("/webhook/facebook")
async def receive_facebook_webhook(request: Request):
    """
    Receives incoming messaging events from Facebook Messenger, WhatsApp, or Instagram.
    Enqueues messages for Gemini Spark to process via MCP.
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"status": "invalid_json"}, status_code=400)

    logger.info(f"Incoming Meta Webhook event: {json.dumps(data)[:200]}...")

    # Parse standard Meta Messenger / WhatsApp event payload
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                message = messaging_event.get("message", {})
                text = message.get("text")

                if sender_id and text:
                    # Enqueue for Gemini Spark to pull and process
                    enqueue_facebook_message(
                        sender_id=sender_id,
                        message_text=text,
                        platform="messenger"
                    )

        return PlainTextResponse("EVENT_RECEIVED", status_code=200)

    elif data.get("object") == "whatsapp_business_account":
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

        return PlainTextResponse("EVENT_RECEIVED", status_code=200)

    return PlainTextResponse("EVENT_RECEIVED", status_code=200)
