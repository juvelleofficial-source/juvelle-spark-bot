# 🤖 PROJECT CONTEXT & VERBATIM MEMORY: Gemini Spark Chat Bot
> **Transferred from Antigravity Session**: `5620c55f-cc1d-46da-8ea4-4c2d911e8508`
> **Session Title**: *Starting Work Without File Analysis*

---

## 📜 Verbatim Handover: What Was Said in the Previous Chat

### The Message You Quoted (Turn 27):
> **Assistant**: "The corrected plan is ready. My apologies for the earlier misunderstanding – I now fully get the architecture:
> **Your MCP server is a dumb bridge.** Gemini Spark (running 24/7 on Google Cloud VMs) is the brain. The server should **never** try to generate AI replies itself. It should:
> 1. **Receive** Meta webhook → **enqueue** the DM in SQLite
> 2. **Push** an SSE notification to Spark saying 'new message arrived'
> 3. **Wait** for Spark to call the MCP tools (`get_pending_messages` → `search_knowledge_base` → `send_facebook_reply`)
> 
> The bug is that `process_and_reply_async()` hijacks this flow and tries to call `google.genai` server-side, which fails on Render.
> Please review the plan and answer the 4 open questions, then I'll execute the fixes."

### The User's Answers (Turn 28 & 35):
> **User**:
> 1. Yes
> 2. No i don't know how to do those stuff, could u do that for me pls?
> 3. Could u test? if it doesn't work, could u create a new one by opening my meta developer ac on profile sahil and so on? if you hit login stuff, just open the login tab for me to sign in (auto login by yourself and if the credentials are wrong like login uname and pass, then open it to me). I thought i had set an permanent token, not sure.
> 4. can u regen token and do things cause i know nothing about it, you have tools for accessing it right? if u can't do it somehow, then yeah ofc just tell me how to do it step by step.

---

## 🏛️ Target Architecture (Gemini Spark MCP Pipeline)

```
Customer DM on Instagram
        │
        ▼ (Meta Webhook POST)
┌────────────────────────────────────────────────────────┐
│   RENDER MCP SERVER (Dumb Bridge + Message Queue)      │
│   1. Webhook receives DM → Enqueue into SQLite inbox   │
│   2. Push SSE notification to Spark: "NEW_MESSAGE"     │
│   3. Expose MCP tools for Spark to call                │
│   4. Dispatch replies via Meta Graph API on command    │
│   ❌ Does NOT generate AI replies                      │
│   ❌ Does NOT need google.genai / API key              │
└──────────────────────────┬─────────────────────────────┘
                           │ SSE / JSON-RPC 2.0
                           ▼
┌────────────────────────────────────────────────────────┐
│         GEMINI SPARK (gemini.google.com — Free VM)     │
│   1. Detects "NEW_MESSAGE" SSE event                   │
│   2. Calls get_pending_facebook_messages()             │
│   3. Calls search_knowledge_base() for RAG facts       │
│   4. Generates brand-grounded AI reply (free LLM)      │
│   5. Calls send_facebook_reply() to dispatch           │
│   6. Calls save_customer_note() for CRM memory         │
└────────────────────────────────────────────────────────┘
```

---

## 🐞 The 5 Concrete Code Fixes to Execute

1. **`mcp_server/server.py`**:
   * Remove `process_and_reply_async()` (L298-316).
   * Remove all `background_tasks.add_task(process_and_reply_async, ...)` calls.
   * Add SSE push broadcasting (`_ACTIVE_SSE_SESSIONS`) to notify Spark of `new_message`.
2. **`api/main.py`**:
   * Remove `live_thread_worker.py` polling task startup (L81-83).
3. **`mcp_server/meta_client.py` & `render.yaml`**:
   * Remove hardcoded `DEFAULT_META_PAGE_ACCESS_TOKEN`.
   * Ensure `render.yaml` treats `META_PAGE_ACCESS_TOKEN` as a private secret.
4. **`.github/workflows/keep_alive.yml`**:
   * Create 5-minute GitHub Actions anti-sleep cron for Render free tier.
5. **Meta Token Test & Regeneration**:
   * Test Meta Page Access Token validity.
   * If expired, use `browseros-neo` (Profile 5: Sahil) to access developers.facebook.com and retrieve/refresh Page Token.

---

## 🛠️ Complete Integrations & Tool Ecosystem
* **`browseros-neo`**: Unrestricted agent browser with persistent profiles (Profile 5: Sahil for Meta).
* **`obsidian-mcp`**: Connected to `C:\Users\sahil\Documents\ObsidianVault`.
* **`n8n-mcp`**: Connected to `http://localhost:5678`.
* **`sequential-thinking`**: Structured multi-step reasoning.
* **`github`**: GitHub repo management.
* **`repomix`**: CLI tool for packing large repos.
* **`es.exe`**: Instant Windows file indexing search.
* **`antigravity_mobile_bridge`**: Mobile remote control bridge.
* **`WirePusher`**: Mobile push notification (`DK3AmpKm6`).
