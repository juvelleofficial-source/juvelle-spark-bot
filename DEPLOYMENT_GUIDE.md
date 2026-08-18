# Juvelle AI Chatbot - 100% Free 24/7 Cloud Deployment Guide

Deploy the Juvelle AI customer support bot to run **24/7 autonomously in the cloud** with **zero local computer dependencies**.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    100% FREE CLOUD STACK                    │
├─────────────────────────────────────────────────────────────┤
│ 1. Vector Database:   Qdrant Cloud (AWS 1GB Cluster)        │
│ 2. AI Reasoning:      Google Gemini Cloud (Sub-second LLM)  │
│ 3. 24/7 Web Server:   Render / Railway / Hugging Face Spaces│
│ 4. Chat Channel:      Meta Graph API (Instagram DM Webhook) │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ (24/7 Webhook)
                              ▼
           [Customer chatting on Instagram / WhatsApp]
              (Your PC is 100% powered off & offline)
```

---

## Option 1: 1-Click Deploy on Render.com (Recommended & Easiest)

Render provides a **100% Free Web Service** with permanent HTTPS.

### Steps:
1. **Push your code to a private or public GitHub repository**:
   ```bash
   git init
   git add .
   git commit -m "feat: complete juvelle cloud chatbot"
   git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPO>.git
   git push -u origin main
   ```
2. **Go to [render.com](https://dashboard.render.com)** and sign in (Free).
3. Click **New +** $\rightarrow$ **Web Service** $\rightarrow$ Select your GitHub repo.
4. Render will automatically detect `render.yaml` or Python runtime:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python -m uvicorn api.main:app --host 0.0.0.0 --port $PORT`
5. Under **Environment Variables**, add:
   - `GEMINI_API_KEY`: `<YOUR_GEMINI_API_KEY>`
   - `QDRANT_URL`: `https://3c502767-14fe-4ed6-81ef-613b5965d897.us-east-1-1.aws.cloud.qdrant.io`
   - `QDRANT_API_KEY`: `<YOUR_QDRANT_API_KEY>`
   - `QDRANT_COLLECTION_NAME`: `juvelle_knowledge`
6. Click **Deploy Web Service**!
   - Your live public HTTPS URL will be ready in ~1 minute (e.g. `https://juvelle-bot.onrender.com`).
   - Webhook URL: `https://juvelle-bot.onrender.com/webhook/instagram-test`

---

## Option 2: 1-Click Deploy on Railway.app

1. Go to [railway.app](https://railway.app) and sign in.
2. Click **New Project** $\rightarrow$ **Deploy from GitHub repo**.
3. Railway automatically uses `railway.toml` and `Dockerfile`.
4. Add the 4 Environment Variables (`GEMINI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION_NAME`).
5. Under **Settings**, click **Generate Domain**.

---

## Option 3: Deploy on Hugging Face Spaces (Docker 16GB RAM Free)

1. Go to [huggingface.co/spaces](https://huggingface.co/spaces) and click **Create new Space**.
2. Space SDK: Select **Docker** (Blank).
3. Space Hardware: **Free (CPU Basic • 2 vCPU • 16GB RAM)**.
4. Clone and push repo files (`git push`).
5. Under **Settings $\rightarrow$ Variables and secrets**, add the environment keys.

---

## Verifying Cloud Health

Once deployed, visit your cloud URL:
- `GET https://<your-cloud-domain>/api/health`
- Response:
  ```json
  {
    "app_name": "Gemini-Spark-Juvelle-Bot",
    "version": "2.1.0",
    "status": "healthy",
    "active_sessions": 0,
    "total_crm_customers": 6,
    "gemini_api_configured": true
  }
  ```
