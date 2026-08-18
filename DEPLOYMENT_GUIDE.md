# Google Gemini Spark MCP Server - 100% Free 24/7 Cloud Deployment Guide

Deploy the MCP Server Bridge for **Google Gemini Spark** (`gemini.google.com`) to run **24/7 in the cloud** with **zero Gemini API keys** and **zero local PC uptime**.

---

## 1. Zero Gemini API Key Paradigm

```
┌───────────────────────────────────────────────────────────────┐
│              GOOGLE GEMINI SPARK (gemini.google.com)          │
│  - Executes 100% of LLM reasoning & Malayalam generation free │
│  - Operates natively in Google's cloud (Zero Gemini API Key)  │
└───────────────────────────────┬───────────────────────────────┘
                                │ (Calls MCP Tools over HTTPS / SSE)
                                ▼
┌───────────────────────────────────────────────────────────────┐
│        YOUR CLOUD MCP SERVER BRIDGE (Render / Railway)        │
│  - Exposes tools to Gemini Spark:                             │
│    • search_knowledge_base() ──► Qdrant Cloud (Vector RAG)    │
│    • get_pending_facebook_messages()                          │
│    • send_facebook_reply()   ──► Meta Graph API               │
│    • save_customer_note()    ──► Customer CRM Intelligence    │
└───────────────────────────────────────────────────────────────┘
                                │
                                ▼
                 [Customer on Instagram / WhatsApp]
```

---

## 2. What is `render.yaml`?

`render.yaml` is simply an **Infrastructure-as-Code blueprint file**. 
When you connect your GitHub repo to [Render.com](https://render.com), Render reads `render.yaml` to automatically:
1. Choose Python 3.11 runtime.
2. Run `pip install -r requirements.txt`.
3. Start the FastAPI MCP Server (`uvicorn api.main:app --port $PORT`).
4. Connect to your free **Qdrant Cloud** cluster.

---

## 3. 1-Click Deployment Steps on Render.com (100% Free)

1. **Push your code to GitHub**:
   ```bash
   git add .
   git commit -m "feat: zero-gemini-key spark mcp server"
   git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/juvelle-mcp-server.git
   git branch -M main
   git push -u origin main
   ```
2. **Go to [render.com](https://dashboard.render.com)** $\rightarrow$ Click **New +** $\rightarrow$ **Blueprint** (or **Web Service**).
3. Select your GitHub repository.
4. Render automatically reads `render.yaml`.
5. Enter your **Qdrant Cloud API Key** under Environment Variables:
   - `QDRANT_API_KEY`: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
   - *(Zero Gemini API Key needed!)*
6. Click **Deploy**!
   - In ~1 minute, your permanent live public HTTPS MCP server will be live:
     - **MCP SSE Endpoint**: `https://<your-app>.onrender.com/mcp/sse`
     - **Meta Webhook URL**: `https://<your-app>.onrender.com/webhook/instagram-test`

---

## 4. Connecting to Gemini Spark at `gemini.google.com`

1. Open `gemini.google.com` in your browser.
2. Go to **Settings & help $\rightarrow$ Connected Apps $\rightarrow$ Custom apps for Spark**.
3. Add your cloud MCP URL:
   `https://<your-app>.onrender.com/mcp/sse`
4. Now you can tell Gemini Spark:
   *"Check for any pending customer messages, search the Juvelle knowledge base for answers, and reply to them."*
   Gemini Spark will autonomously run the tools in Google Cloud for $0.
