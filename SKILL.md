---
name: gemini-spark-mcp-integration
description: Comprehensive guide and implementation blueprints for connecting Google Gemini Spark (autonomous agent at gemini.google.com) to external apps, Facebook Developer (Meta Graph API / WhatsApp / Messenger), and custom RAG knowledge bases via Model Context Protocol (MCP) with zero Gemini API keys.
---

# Google Gemini Spark MCP Integration & Cloud RAG Guide

## 1. Core Principles: The "Zero Gemini API Key" Paradigm
- **Gemini Spark Autonomous Agent**: Operates directly inside Google's cloud ecosystem at `gemini.google.com`. Google provides the LLM compute and reasoning natively within the web environment for free.
- **Custom Apps for Spark**: Users can connect external custom services via Model Context Protocol (MCP) under **Settings & help $\rightarrow$ Connected Apps $\rightarrow$ Custom apps for Spark**.
- **Role of the MCP Server**: You host a lightweight backend (via Cloudflare Tunnel or free cloud tiers like Render/Railway) that exposes tools (e.g. `get_pending_facebook_messages`, `search_knowledge_base`, `send_facebook_reply`, `save_customer_note`).
- **No Gemini API Required for Spark**: Because Gemini Spark executes reasoning inside Google's cloud environment, **no paid Gemini API key is needed in your codebase**.

---

## 2. Permanent Free Cloud Vector Database: Qdrant Cloud
- **Permanent Free Tier**: 1 GB RAM / 4 GB Disk cluster forever on AWS (`aws.cloud.qdrant.io`) with zero credit card required.
- **Python Client**: `qdrant-client`
- **Embedding Dimensions**: 768 (Cosine Distance).
- **Collection Setup**:
  ```python
  from qdrant_client import QdrantClient
  from qdrant_client.models import Distance, VectorParams, PointStruct

  client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
  client.create_collection(
      collection_name="juvelle_knowledge",
      vectors_config=VectorParams(size=768, distance=Distance.COSINE)
  )
  ```
- **Live Hybrid RAG Query**:
  ```python
  results = client.query_points(
      collection_name="juvelle_knowledge",
      query=query_vector,
      limit=3
  )
  ```

---

## 3. Session Lifecycle & Anti-Repetitive Greeting Engine
- **3-Hour Active Shopping Window (10,800s)**:
  - **Turn 1 (First Contact)**: Warm branded introductory welcome (e.g. *"Hey there! Welcome to Juvelle 🌸 We specialize in daily and office wear Churidar tops. How can I help you today? ✨"*).
  - **Active Dialogue (< 3 hours)**: Customers deliberate, compare sizes, or ask family. When they reply back, the bot **never repeats** "Welcome to Juvelle" or re-introduces the company. Answers directly and politely.
  - **Mid-Conversation "Hi/Hey"**: Natural short acknowledgment (e.g. *"Hey! Yes, tell me? ✨"*).
  - **Returning Customer (> 3 hours / days)**: Warm welcome back re-engagement (*"Hey again! Welcome back to Juvelle ✨"*), referencing saved size preferences if known.

---

## 4. Automated Customer CRM Profiling
Extracts demographic and purchase signals in real-time into SQLite `customer_crm`:
- **Sizes**: `XS`, `S`, `M`, `L`, `XL`, `XXL`, `3XL`
- **Fabrics**: `Cotton`, `Rayon`, `Linen`, `Silk`
- **Kerala Locations**: `Kochi`, `Calicut`, `Trivandrum`, `Thrissur`, etc.
- **Stages**: `New Lead`, `Browsing`, `Ready to Order`, `Existing Customer`, `Support`
- **REST APIs**: `GET /api/crm/customers`, `GET /api/crm/customers/{user_id}`, `GET /api/crm/stats`.

---

## 5. Manglish Natural Language Formatting & Sanitizer Rules
When generating responses in Manglish (Malayalam written in Latin script):
1. **Pure Script Purity**: NEVER mix Malayalam Unicode characters (`\u0D00-\u0D7F`) inside English letters (e.g., avoid `cheyyേണ്ടathu` $\rightarrow$ use `cheyyendathu`).
2. **Zero Hyphens (`-`)**: Real humans never type hyphens attached to nouns/suffixes.
   - *Wrong*: `Juvelle-te`, `Kerala-il`, `delivery-kku`, `available-aanu`.
   - *Right*: `Juvelle inte`, `Kerala yil` / `Keralathil`, `deliverykku`, `available aanu`.
3. **Possessive Suffix**: Always use `inte` (e.g., `Juvelle inte`), never `-te` or `Juvellete`.
4. **Natural Human Boutique Sales Phrasing**:
   - Instead of stiff textbook Malayalam (*"Enikku enthu sahayam aanu cheyyendathu?"*), use natural DM sales coordination:
     - *"Illa, njan Juvelle inte AI assistant aanu! Enthaanu nokkunnath? ✨"*
     - *"Enganeya help cheyyendath? ✨"*
     - *"Enthelum models kaanikkatte? ✨"*
5. **Deterministic Sanitizer**: Run a regex cleaner on every LLM output to catch any stray token unicode bleed or hyphenation before sending to the customer.

---

## 6. Google GenAI Active Candidate Model Cascade
For local tester UIs, fallbacks, or webhook endpoints, use a rapid cascade over active models to ensure sub-second response times without 429 quota exhaustion:

| Priority | Model Identifier | Purpose |
| :--- | :--- | :--- |
| **1st (Fastest)** | `gemini-flash-lite-latest` | Sub-second latency, generous free tier limits |
| **2nd** | `gemini-3.5-flash-lite` | Efficient lightweight reasoning |
| **3rd** | `gemini-3.6-flash` | High-accuracy multimodal reasoning |
| **4th** | `gemini-3.5-flash` | General flash candidate |
| **Deprecated** | `gemini-1.5-flash`, `gemini-2.0-flash`, `gemini-2.5-flash` | Return 404 NOT_FOUND |

---

## 7. Standard MCP Server Protocol Specification & Handshake Probes
When Google Gemini Spark registers a custom app at `gemini.google.com`, it sends automated validation probes. The server **must** support the following:
1. **`HEAD /mcp/sse`**: Returns HTTP `200 OK` with `media_type="text/event-stream"`.
2. **`GET /mcp/sse`**: Emits endpoint discovery `event: endpoint\ndata: /mcp/messages\n\n` and keep-alive heartbeats every 15s.
3. **`POST /mcp/sse` & `POST /mcp/messages`**: Accepts JSON-RPC 2.0 requests (`initialize`, `tools/list`, `tools/call`, `ping`).
4. **`GET /.well-known/oauth-protected-resource`**: Returns `{ "resource": "<base_url>", "authorization_servers": [] }`.
5. **CORS Headers**: `Access-Control-Allow-Origin: *`.

---

## 8. MCP Tools Manifest Exposed to Gemini Spark
1. **`get_pending_facebook_messages`**: Fetches unreplied inquiries from the SQLite queue.
2. **`search_knowledge_base`**: Executes hybrid dense cosine (Qdrant Cloud) and lexical BM25 search over enterprise RAG documents.
3. **`send_facebook_reply`**: Calls Meta Graph API to send the grounded answer and updates queue status to `replied`.
4. **`save_customer_note`**: Persists CRM customer preferences and facts in long-term memory.

---

## 9. 24/7 Cloud Deployment & True External Keep-Alive Architecture
- **Vector DB**: Qdrant Cloud AWS cluster (runs 24/7 independently in cloud).
- **Backend Host**: Deploy repository to Render (`render.yaml`) / Railway (`railway.toml`) / Fly.io / HF Spaces (`Dockerfile`).
- **External Keep-Alive Engine**:
  - Internal self-pings within Render container processes do not pass through Render's reverse proxy edge and do not reset the 15-minute idle counter.
  - Dedicated **GitHub Actions Workflow (`.github/workflows/keep_alive.yml`)** runs every 5 minutes (`*/5 * * * *`) on GitHub's free runners, sending external HTTPS requests to `/api/health`, `/health`, and `/mcp/sse`.
  - External uptime monitors (UptimeRobot, Cron-Job.org) support both `GET` and `HEAD` probes across all health routes without 405 errors.
- **Zero Gemini API Key**: Gemini Spark provides 100% of LLM compute on `gemini.google.com`.
- **Zero Local Dependency**: Once deployed to cloud hosting, local computer can be completely powered off.

