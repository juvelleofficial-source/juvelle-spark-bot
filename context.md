# Comprehensive System Context & Architectural Blueprint

## 1. Project Overview & Core Philosophy
This project implements an enterprise-grade, 100% free **Model Context Protocol (MCP) Bridge & Autonomous AI Agent System** connecting **Google Gemini Spark** with **Facebook Developer (Meta Graph API)**, **WhatsApp Business API**, **Pinecone Cloud Vector Database**, and a local **Instagram DM Simulator / Tester**.

### 1.1 The "Zero Gemini API Key" Paradigm
- **Standard Gemini API**: Requires an API key from Google AI Studio, pay-per-token pricing, billing setups, and rate limits.
- **Google Gemini Spark**: Google's autonomous background agent operating at `gemini.google.com`. Google provides the reasoning compute natively within the web environment for free.
- **The MCP Bridge**: By registering a custom MCP Server endpoint in Gemini Spark (`Settings -> Connected Apps -> Custom apps for Spark`), Gemini Spark acts as the autonomous intelligence layer that drives external applications, Meta messaging, and document querying without consuming user API credits.

---

## 2. System Architecture & Component Interactions

```
+-----------------------------------------------------------------------------------+
|                            META DEVELOPER ECOSYSTEM                               |
|        (Facebook Messenger / WhatsApp Business / Instagram Direct / Tester)        |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          | Webhooks (POST /webhook/facebook & /webhook/instagram-test)
                                          v
+-----------------------------------------------------------------------------------+
|                      FREE CLOUD FASTAPI MCP & RAG SERVER                          |
|                                                                                   |
|  +---------------------------+       +-----------------------------------------+  |
|  |  Meta Webhook Controller  | ----> |  SQLite Message Queue (mcp_inbox.db)    |  |
|  +---------------------------+       +-----------------------------------------+  |
|                                                           ^                       |
|  +---------------------------+                            | Pulls & Updates       |
|  |  Juvelle Agent Engine     |                            v                       |
|  |  (Instagram DM Persona)   | <---> +-----------------------------------------+  |
|  +---------------------------+       |     MCP Protocol Engine (FastAPI)       |  |
|         |                            |  - GET  /mcp/sse                        |  |
|         v                            |  - POST /mcp/messages                   |  |
|  +---------------------------+       +-----------------------------------------+  |
|  | Pinecone Vector Database  |                            |                       |
|  | (gemini-memory 768-dim)   |                            v                       |
|  +---------------------------+       +-----------------------------------------+  |
|         |                            |  Meta Graph API Dispatcher              |  |
|         v                            |  (graph.facebook.com/v19.0)             |  |
|  +---------------------------+       +-----------------------------------------+  |
|  | Local Zero-Cost Hybrid RAG|                                                    |
|  | (BM25 + Cosine + RRF)     |                                                    |
|  +---------------------------+                                                    |
+-----------------------------------------+-----------------------------------------+
                                          ^
                                          | SSE / JSON-RPC 2.0
                                          v
+-----------------------------------------------------------------------------------+
|                          GOOGLE GEMINI SPARK AGENT                                |
|                         (Hosted at gemini.google.com)                             |
|                                                                                   |
|  1. Discovers tools via MCP Tools Manifest                                        |
|  2. Calls `get_pending_facebook_messages` to check inbox                          |
|  3. Calls `search_knowledge_base` to retrieve grounded RAG facts                  |
|  4. Autonomously formulates human-like grounded responses                         |
|  5. Calls `send_facebook_reply` to dispatch the reply via Meta Graph API           |
|  6. Calls `save_customer_note` to update long-term CRM memory                     |
+-----------------------------------------------------------------------------------+
```

---

## 3. Vector Database & Knowledge Retrieval (Pinecone RAG)

### 3.1 Pinecone Cloud Integration
- **Index Name**: `gemini-memory`
- **Host Endpoint**: `https://gemini-memory-4gbye74.svc.aped-4627-b74a.pinecone.io`
- **Vector Dimension**: `768` floats (Dense, on-demand, AWS `us-east-1`)
- **Authentication**: `Api-Key` HTTP Header authentication
- **Client Implementation**: `retrieval/pinecone_client.py`

### 3.2 Juvelle Brand Knowledge Base (Seeded Vectors)
1. **`juvelle_brand_core`**: Premium daily & office wear Churidar tops (Price range ₹399 - ₹899).
2. **`juvelle_delivery_shipping`**: Exclusive delivery to **Kerala ONLY** via Delhivery courier service (dispatched next working day). Politely declines outside orders (Bangalore, Mumbai, Dubai, etc.).
3. **`juvelle_payment_policy`**: Online payment only (UPI / GPay / PhonePe / Paytm / Bank Transfer). NO Cash on Delivery (COD) to ensure faster next-day dispatch.
4. **`juvelle_ordering_process`**: Simple 3-step ordering process (Screenshot + Size in DM -> Availability & Payment Confirmation -> Next-day dispatch).
5. **`juvelle_product_catalog`**: Breathable cotton and premium rayon blends tailored for all-day comfort.

---

## 4. Juvelle AI Customer Service Agent (`core/juvelle_agent.py`)

- **Persona**: "Juvelle Support" — warm, polite, helpful, quietly confident, speaking like a high-end boutique owner.
- **Tone & Formatting**: 2-3 short sentences, gentle emojis (`✨`, `🌸`, `🧵`, `📦`), never aggressive or pushy.
- **Dynamic Memory**: Tracks session dialogue turns using `memory.short_term_memory` and synchronizes to local SQLite storage.
- **Response Format**: Outputs structured array of messages matching Instagram DM bubble splitting.

---

## 5. Instagram Tester & Simulation Protocol

- **Tester Location**: `C:\Users\sahil\antigravity\instagram_tester`
- **Config**: `C:\Users\sahil\antigravity\instagram_tester\config.json`
- **Webhook Endpoint**: `POST http://127.0.0.1:8000/webhook/instagram-test`
- **Supported Test Scenarios**:
  1. *Greeting & Catalog*: "Hi, what tops do you have?"
  2. *Territory Restriction*: "Can you ship to Bangalore?"
  3. *Payment & COD Policy*: "Do you have COD?"
  4. *Order Placement Workflow*: "How do I order this top?"
  5. *Pricing & Availability*: "What is the price of your tops?"
  6. *Website Query*: "What is your website link?"

---

## 6. Model Context Protocol (MCP) Server Specifications

### 6.1 Protocol Endpoints
- **SSE Stream Endpoint**: `GET /mcp/sse`
  - Purpose: Provides the initial handshake for Gemini Spark and streams server-sent events for keep-alive ping heartbeats.
  - Initial Event: `event: endpoint \n data: /mcp/messages`
- **JSON-RPC Handler**: `POST /mcp/messages`
  - Standard JSON-RPC 2.0 protocol handler.
  - Supports methods: `initialize`, `tools/list`, `tools/call`, `ping`, and `notifications/initialized`.

### 6.2 Exposed MCP Tools Manifest

#### `get_pending_facebook_messages`
- **Description**: Retrieves pending customer inquiries received from Facebook Messenger, WhatsApp, or Instagram via Webhooks.
- **Parameters**: `limit` (integer, optional, default: 5).

#### `search_knowledge_base`
- **Description**: Performs a hybrid semantic vector search (Pinecone / Local) and lexical search across internal enterprise documents.
- **Parameters**: `query` (string, required), `top_k` (integer, optional, default: 3).

#### `send_facebook_reply`
- **Description**: Dispatches the AI-generated reply back to the customer via Meta Graph API and marks the message as resolved.
- **Parameters**: `message_id` (string, required), `recipient_id` (string, required), `reply_text` (string, required).

#### `save_customer_note`
- **Description**: Persists customer preferences or CRM details into long-term SQLite memory.
- **Parameters**: `sender_id` (string, required), `customer_name` (string, optional), `notes` (string, required).

---

## 7. Meta Developer Integration

### 7.1 Webhook Handshake (`GET /webhook/facebook`)
- Meta sends a verification request with query parameters: `hub.mode`, `hub.verify_token`, and `hub.challenge`.
- The server validates `hub.verify_token == META_VERIFY_TOKEN` and responds with the raw `hub.challenge` string.

### 7.2 Incoming Event Ingestion (`POST /webhook/facebook`)
- Handles incoming `page` (Messenger / Instagram) and `whatsapp_business_account` events.
- Extracts `sender.id` and `message.text`, automatically queuing them into `mcp_inbox.db`.

### 7.3 Outbound Message Dispatch (`meta_client.py`)
- Sends POST requests to `https://graph.facebook.com/v19.0/me/messages` using `META_PAGE_ACCESS_TOKEN`.
- Includes automated mock/simulation mode for offline local development when tokens are not yet configured.

---

## 8. Multi-Tier Memory Engine

### 8.1 Short-Term Memory Buffer
- In-memory sliding window holding recent conversation turns (`memory/short_term_memory.py`).
- Enforces strict token limit boundaries to prevent context overflow.

### 8.2 Long-Term Persistent Memory
- Backed by SQLite database (`data/memory.db`).
- Stores historical conversation turns, user entity profiles, and CRM notes (`memory/long_term_memory.py`).

### 8.3 Episodic Memory Consolidation
- Summarizes multi-turn sessions into concise user preference vectors (`memory/spark_memory_consolidator.py`).

---

## 9. 100% Free Cloud Deployment Blueprint

| Platform | Free Tier Resource | Purpose | Configuration |
| :--- | :--- | :--- | :--- |
| **Pinecone Serverless** | 1 Index, 2GB Storage, 100K queries/mo | Production Vector Database | `gemini-memory` (768-dim) |
| **Hugging Face Spaces** | 2 vCPU, 16 GB RAM, Unlimited time | Full MCP Server + FastAPI | `Dockerfile` (Port 7860 / 8000) |
| **Render.com** | 512 MB RAM, 750 free hours/month | Standby MCP API Server | `Dockerfile` / Web Service |
| **Vercel** | 100 GB Bandwidth, Edge Functions | Frontend UI + Static Hosting | `vercel.json` |
| **Google Gemini Spark** | Free on `gemini.google.com` | Autonomous AI Reasoning & Tool Execution | Connected Apps (MCP URL) |

---

## 10. Project Directory Structure

```
Gemini Spark Chat Bot/
├── api/
│   ├── main.py                  # FastAPI entrypoint (Web App + MCP router + Instagram Webhooks)
│   └── schemas.py               # Pydantic request/response schemas
├── config/
│   └── settings.py              # Environment variables & runtime configurations
├── core/
│   ├── failover_client.py       # Multi-model zero-cost failover engine
│   ├── juvelle_agent.py         # Juvelle Customer Support Agent & Instagram persona engine
│   ├── orchestrator.py          # Grounded RAG chat orchestrator
│   └── router.py                # Complexity query classifier
├── data/
│   ├── sample_docs.json         # Enterprise knowledge base documents
│   ├── mcp_inbox.db             # SQLite inbox for incoming Meta messages
│   └── memory.db                # SQLite long-term user memory
├── frontend/
│   ├── app.js                   # Glassmorphic UI logic & SSE chat client
│   ├── index.html               # Web UI interface
│   └── style.css                # Premium styling & dark mode tokens
├── ingestion/
│   ├── batch_embedder.py        # Dense vector embedding generator
│   ├── chunker.py               # Semantic document chunker
│   ├── ingestion_job.py         # Distributed document ingestion pipeline
│   ├── spark_session.py         # Zero-cost distributed Spark emulator
│   └── vector_indexer.py        # Vector index synchronization & storage
├── mcp_server/
│   ├── __init__.py              # MCP server package exports
│   ├── message_queue.py         # Meta inbox queue & CRM persistence
│   ├── meta_client.py           # Meta Graph API v19.0 client & simulator
│   ├── server.py                # Standard MCP SSE + JSON-RPC protocol server
│   └── tools_registry.py        # Tool schemas & execution handlers
├── memory/
│   ├── long_term_memory.py      # SQLite persistent memory store
│   ├── short_term_memory.py     # In-memory sliding context window
│   └── spark_memory_consolidator.py # Episodic memory consolidation
├── retrieval/
│   ├── hybrid_ranker.py         # Reciprocal Rank Fusion (RRF) algorithm
│   ├── pinecone_client.py       # Pinecone Cloud Vector REST client (gemini-memory)
│   └── vector_retriever.py      # Dense + lexical hybrid search engine
├── tests/
│   ├── test_mcp_server.py       # MCP & Meta Webhook automated tests (4 tests)
│   └── test_system.py           # Core system unit tests (7 tests)
├── .env.example                 # Sample configuration template
├── context.md                   # Complete architectural system context
├── Dockerfile                   # 16GB Container deployment manifest
├── requirements.txt             # Python project dependencies
└── vercel.json                  # Vercel serverless deployment config
```

---

## 11. Automated Testing & Verification Commands

```bash
# Run MCP & Meta Webhook tests:
python -m unittest tests.test_mcp_server

# Run core RAG & memory system tests:
python -m unittest tests.test_system

# Seed and verify Pinecone vector knowledge:
python -c "from retrieval.pinecone_client import seed_juvelle_knowledge_to_pinecone; seed_juvelle_knowledge_to_pinecone()"
```
