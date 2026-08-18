# Comprehensive System Context & Architectural Blueprint

## 1. Project Overview & Core Philosophy
This project implements a production-grade, 100% free **Model Context Protocol (MCP) Bridge, Autonomous AI Agent & Customer CRM System** connecting **Google Gemini Spark** (`gemini.google.com`) with **Facebook Developer (Meta Graph API)**, **WhatsApp Business API**, **Qdrant Cloud Vector Database (AWS)**, and a live **Instagram DM Simulator / Tester**.

### 1.1 The "Zero Gemini API Key" Paradigm
- **Standard Gemini API**: Requires an API key from Google AI Studio, pay-per-token pricing, and quota limits.
- **Google Gemini Spark**: Google's autonomous background agent operating directly at `gemini.google.com`. Google provides 100% of the LLM compute, reasoning, and response generation natively within Google's cloud for free.
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
|                   24/7 CLOUD FASTAPI MCP & RAG SERVER (Render / Railway)          |
|                                                                                   |
|  +---------------------------+       +-----------------------------------------+  |
|  |  Meta Webhook Controller  | ----> |  SQLite Message Queue (mcp_inbox.db)    |  |
|  +---------------------------+       +-----------------------------------------+  |
|                                                           ^                       |
|  +---------------------------+                            | Pulls & Updates       |
|  |  Session Lifecycle Engine |                            v                       |
|  |  (3-Hour Shopping Window) | <---> +-----------------------------------------+  |
|  +---------------------------+       |     MCP Protocol Engine (FastAPI)       |  |
|         |                            |  - GET  /mcp/sse                        |  |
|         v                            |  - POST /mcp/messages                   |  |
|  +---------------------------+       +-----------------------------------------+  |
|  |  Customer CRM Profiler    |                            |                       |
|  |  (Sizes, Fabrics, Stage)  |                            v                       |
|  +---------------------------+       +-----------------------------------------+  |
|         |                            |  Meta Graph API Dispatcher              |  |
|         v                            |  (graph.facebook.com/v19.0)             |  |
|  +---------------------------+       +-----------------------------------------+  |
|  | Qdrant Cloud Vector DB    |                                                    |
|  | (juvelle_knowledge 768-dim|                                                    |
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
|  3. Calls `search_knowledge_base` to retrieve grounded RAG facts from Qdrant Cloud |
|  4. Autonomously formulates human-like grounded responses                         |
|  5. Calls `send_facebook_reply` to dispatch the reply via Meta Graph API           |
|  6. Calls `save_customer_note` to update long-term CRM memory                     |
+-----------------------------------------------------------------------------------+
```

---

## 3. Vector Database & Knowledge Retrieval (Qdrant Cloud RAG)

### 3.1 Qdrant Cloud Permanent Free Tier
- **Provider**: Qdrant Cloud on AWS (`aws.cloud.qdrant.io`)
- **Collection Name**: `juvelle_knowledge`
- **Cluster Endpoint**: `https://3c502767-14fe-4ed6-81ef-613b5965d897.us-east-1-1.aws.cloud.qdrant.io`
- **Vector Dimension**: `768` dimensions, `Distance.COSINE`
- **Client**: `qdrant-client` (Async & Sync support)
- **Local Fallback**: In-memory dense cosine similarity + BM25 keyword matching via Reciprocal Rank Fusion (RRF).

### 3.2 Seeded Juvelle Brand Knowledge Base
1. **`juvelle_brand_core`**: Premium daily & office wear Churidar tops (Price range ₹399 - ₹899).
2. **`juvelle_delivery_shipping`**: Exclusive delivery to **Kerala ONLY** via Delhivery courier service (2-3 business days, ₹50 standard shipping). Politely declines outside orders (Bangalore, Mumbai, Dubai, etc.).
3. **`juvelle_payment_policy`**: Online payment only (UPI / GPay / PhonePe / Paytm / Bank Transfer). NO Cash on Delivery (COD).
4. **`juvelle_ordering_process`**: Simple 3-step ordering process (Screenshot + Size in DM -> Availability & Payment Confirmation -> Next-day dispatch).
5. **`juvelle_product_catalog`**: Breathable cotton and premium soft rayon blends.

---

## 4. Session Lifecycle & Anti-Repetitive Greeting Engine

### 4.1 3-Hour Active Shopping Window (10,800s)
- **Turn 1 (First Contact)**:
  - Delivers a warm brand welcome (*"Hey there! Welcome to Juvelle 🌸 We specialize in daily and office wear Churidar tops. How can I help you today? ✨"*).
- **Active Dialogue (< 3 Hours Inactivity)**:
  - Customers frequently take 1–2 hours to ask parents or deliberate on sizing.
  - **Zero Repeated Greetings**: The bot jumps straight into answering queries without re-introducing the company.
- **Mid-Conversation "Hi/Hey"**:
  - Natural human acknowledgment (*"Hey! Yes, tell me? ✨"*) without restarting the brand intro.
- **Returning Customer (> 3 Hours Inactivity)**:
  - Warm re-engagement greeting (*"Hey again! Welcome back to Juvelle ✨"*), referencing saved size preferences if known.

---

## 5. Customer CRM Profiling & Filter REST APIs

### 5.1 Automated Entity & Intent Extraction
- **Sizes**: `XS`, `S`, `M`, `L`, `XL`, `XXL`, `3XL`
- **Fabrics**: `Cotton`, `Rayon`, `Linen`, `Silk`
- **Kerala Locations**: `Kochi`, `Calicut`, `Trivandrum`, `Thrissur`, `Kannur`, etc.
- **Lifecycle Stages**: `New Lead`, `Browsing`, `Ready to Order`, `Existing Customer`, `Support`

### 5.2 CRM REST Endpoints
- `GET /api/crm/customers`: Filter by stage, preferred size, or location.
- `GET /api/crm/customers/{user_id}`: Full customer dossier and past dialogue turns.
- `GET /api/crm/stats`: Real-time stage distribution and size analytics.
- `POST /api/crm/customers/{user_id}/tag`: Add custom tags and CRM sales notes.

---

## 6. Manglish Natural Language Formatting & Sanitizer

1. **Pure Script Purity**: Prevents Malayalam Unicode bleeding (`\u0D00-\u0D7F`) into Latin characters.
2. **Zero Hyphens (`-`)**: Eliminates unnatural machine hyphens (e.g. transforms `Juvelle-te` $\rightarrow$ `Juvelle inte`, `Kerala-il` $\rightarrow$ `Kerala yil`, `delivery-kku` $\rightarrow$ `deliverykku`).
3. **Possessive Suffix**: Enforces `inte` over `-te`.
4. **Active Candidate Cascade**: `gemini-flash-lite-latest` $\rightarrow$ `gemini-3.5-flash-lite` $\rightarrow$ `gemini-3.6-flash` $\rightarrow$ `gemini-3.5-flash`.

---

## 7. Model Context Protocol (MCP) Server Specifications

### 7.1 Protocol Endpoints
- **SSE Stream Endpoint**: `GET /mcp/sse` (Handshake + discovery + 15s keep-alive).
- **JSON-RPC Handler**: `POST /mcp/messages` & `POST /mcp/sse` (Streamable HTTP).
- **OAuth Discovery**: `GET /.well-known/oauth-protected-resource`.

### 7.2 Exposed MCP Tools Manifest
1. `get_pending_facebook_messages`: Fetches unreplied customer inquiries from SQLite queue.
2. `search_knowledge_base`: Dense Qdrant Cloud cosine + BM25 keyword hybrid search.
3. `send_facebook_reply`: Dispatches response via Meta Graph API v19.0.
4. `save_customer_note`: Persists customer preferences into long-term CRM memory.

---

## 8. 1-Click 24/7 Pure Cloud Deployment Suite

| File | Platform / Target | Purpose |
| :--- | :--- | :--- |
| **`render.yaml`** | Render.com | 1-Click Blueprint for 100% Free Web Service with permanent HTTPS |
| **`railway.toml`** | Railway.app | Native Railway container deployment specification |
| **`Dockerfile`** | HF Spaces / Cloud Run | Universal Python 3.11 container with dynamic `$PORT` binding |
| **`DEPLOYMENT_GUIDE.md`** | Multi-Cloud | Visual step-by-step 1-click cloud deployment guide |
| **`.gitignore`** | Git / GitHub | Strictly excludes `.env`, secrets, local binaries, and logs |

---

## 9. Automated Testing & Verification Commands

```bash
# Test Session Lifecycle, Anti-Repetitive Greetings, Concurrency & CRM:
python scratch/test_session_and_crm.py

# Test Live HTTP Endpoints on Running Server:
python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health').read().decode())"

# Synchronize all code and configs to OneDrive Cloud Backup:
python scratch/sync_to_onedrive_backup.py
```
