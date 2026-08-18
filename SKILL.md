---
name: gemini-spark-mcp-integration
description: Comprehensive guide and implementation blueprints for connecting Google Gemini Spark (autonomous agent at gemini.google.com) to external apps, Facebook Developer (Meta Graph API / WhatsApp / Messenger), and custom RAG knowledge bases via Model Context Protocol (MCP) with zero Gemini API keys.
---

# Google Gemini Spark MCP Integration & Facebook Developer Guide

## 1. Core Principles: The "Zero Gemini API Key" Paradigm
- **Gemini Spark Autonomous Agent**: Operates directly inside Google's cloud ecosystem at `gemini.google.com`. Google provides the LLM compute and reasoning natively within the web environment for free.
- **Custom Apps for Spark**: Users can connect external custom services via Model Context Protocol (MCP) under **Settings & help $\rightarrow$ Connected Apps $\rightarrow$ Custom apps for Spark**.
- **Role of the MCP Server**: You host a lightweight backend (on 100% free cloud tiers like Hugging Face Spaces 16GB or Render) that exposes tools (e.g. `get_pending_messages`, `search_knowledge_base`, `send_facebook_reply`).
- **No Gemini API Required**: Because Gemini Spark executes reasoning inside Google's environment, **no paid Gemini API key is needed in your codebase**.

---

## 2. Standard MCP Server Protocol Specification

Gemini Spark connects over HTTP / Server-Sent Events (SSE) using JSON-RPC 2.0.

### 2.1 Protocol Endpoints
- **SSE Stream**: `GET /mcp/sse`
  - Emits initial endpoint discovery: `event: endpoint\ndata: /mcp/messages\n\n`
  - Maintains keep-alive ping heartbeats.
- **JSON-RPC Handler**: `POST /mcp/messages`
  - Handles `initialize`, `tools/list`, `tools/call`, `ping`, and `notifications/initialized`.

### 2.2 Standard MCP Handshake
```python
# Initialization Request from Gemini Spark:
# {"jsonrpc": "2.0", "id": "1", "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}

# Handshake Response:
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {"listChanged": False}
    },
    "serverInfo": {
      "name": "Gemini-Spark-MCP-Server",
      "version": "1.0.0"
    }
  }
}
```

---

## 3. Meta / Facebook Developer (Graph API) Bridge

### 3.1 Webhook Verification Handshake (`GET /webhook/facebook`)
```python
@mcp_router.get("/webhook/facebook")
def verify_facebook_webhook(hub_mode: str = Query(None, alias="hub.mode"),
                            hub_verify_token: str = Query(None, alias="hub.verify_token"),
                            hub_challenge: str = Query(None, alias="hub.challenge")):
    if hub_mode == "subscribe" and hub_verify_token == os.getenv("META_VERIFY_TOKEN", "secret_token"):
        return PlainTextResponse(content=hub_challenge or "")
    raise HTTPException(status_code=403, detail="Verification token mismatch")
```

### 3.2 Incoming Message Buffer Queue (`POST /webhook/facebook`)
Incoming customer inquiries from Facebook Messenger or WhatsApp are enqueued in SQLite (`mcp_inbox.db`) to decouple synchronous webhooks from agentic tool polling:
```python
def enqueue_facebook_message(sender_id: str, message_text: str, platform: str = "messenger") -> str:
    # Inserts record with status = 'pending'
```

### 3.3 Outbound Message Dispatch via Meta Graph API v19.0
```python
def send_meta_graph_reply(recipient_id: str, message_text: str) -> dict:
    token = os.getenv("META_PAGE_ACCESS_TOKEN")
    if not token:
        # Fallback simulator for local/test development
        return {"status": "success", "mode": "simulated", "recipient_id": recipient_id}
    
    url = "https://graph.facebook.com/v19.0/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": "RESPONSE",
        "message": {"text": message_text}
    }
    # Send HTTP POST with Bearer Token
```

---

## 4. MCP Tools Manifest Exposed to Gemini Spark

The MCP server exposes standard tools in `tools/list`:

1. **`get_pending_facebook_messages`**:
   - Fetches unreplied inquiries from the SQLite queue.
   - Params: `limit` (int, default: 5).
2. **`search_knowledge_base`**:
   - Executes hybrid dense cosine and lexical BM25 search over enterprise RAG documents.
   - Params: `query` (str), `top_k` (int, default: 3).
3. **`send_facebook_reply`**:
   - Calls Meta Graph API to send the grounded answer and updates queue status to `replied`.
   - Params: `message_id` (str), `recipient_id` (str), `reply_text` (str).
4. **`save_customer_note`**:
   - Persists CRM customer preferences and facts in long-term memory.
   - Params: `sender_id` (str), `notes` (str).

---

## 5. End-to-End Execution Flow

```
Customer Message (Facebook / WhatsApp)
      │
      ▼
Meta Webhook POST /webhook/facebook
      │
      ▼
SQLite Buffer Queue (mcp_inbox.db)
      │
      ▼
Gemini Spark pulls: `get_pending_facebook_messages()`
      │
      ▼
Gemini Spark queries: `search_knowledge_base(query)`
      │
      ▼
Gemini Spark autonomous reasoning (Google Compute / Free)
      │
      ▼
Gemini Spark dispatches: `send_facebook_reply(recipient_id, text)`
      │
      ▼
Meta Graph API delivers reply to Customer
```

---

## 6. How to Register in Gemini Spark (`gemini.google.com`)

1. Expose your server publicly (e.g. Hugging Face Spaces or `ngrok http 8000`).
2. Go to **`gemini.google.com` $\rightarrow$ Settings & help $\rightarrow$ Connected Apps $\rightarrow$ Custom apps for Spark**.
3. Click **Add a custom app**.
4. Enter your SSE URL: `https://your-public-url.com/mcp/sse`.
5. Spark will automatically discover the tools and run background workflows autonomously.

---

## 7. 100% Free Hosting Deployment

- **Hugging Face Spaces**: Deploy via `Dockerfile` with 2 vCPUs and 16 GB RAM at $0 cost.
- **Render.com**: Deploy as a free web service with automatic SSL.
- **Vercel**: Deploy static frontend UI at zero cost.
