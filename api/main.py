import os
import json
import logging
from typing import AsyncGenerator, Optional, List
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.settings import settings
from api.schemas import ChatRequest, IngestionRequest, IngestionResponse, MemoryInspectResponse, HealthResponse
from core.orchestrator import orchestrator
from memory.short_term_memory import memory_manager
from memory.long_term_memory import (
    get_user_profile,
    get_customer_crm,
    list_customers_crm,
    get_crm_stats,
    upsert_customer_crm
)
from memory.spark_memory_consolidator import consolidate_user_memories_spark
from ingestion.ingestion_job import run_ingestion_pipeline
from ingestion.vector_indexer import _LOCAL_VECTOR_STORE
from mcp_server.server import mcp_router
from core.juvelle_agent import generate_juvelle_response

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("FastAPIServer")

app = FastAPI(
    title="Gemini Spark Custom MCP & Enterprise RAG Server",
    version="2.1.0",
    description="100% Free Production-Grade MCP Bridge connecting Google Gemini Spark with Facebook Developer (Meta Graph API), Qdrant Cloud RAG, and Session Lifecycle CRM."
)

# CORS middleware for local frontend & Instagram tester connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Gemini Spark MCP & Meta Webhook Router
app.include_router(mcp_router)

import asyncio
import httpx

async def keep_alive_background_worker():
    """Periodically pings public URL every 10 minutes to prevent Render free-tier idle sleep."""
    await asyncio.sleep(30)
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "https://juvelle-spark-bot.onrender.com")
    health_endpoint = f"{render_url.rstrip('/')}/api/health"
    
    while True:
        try:
            await asyncio.sleep(600)  # 10 minutes
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(health_endpoint)
                logger.info(f"Keep-alive self ping to {health_endpoint} [status: {resp.status_code}]")
        except Exception as e:
            logger.debug(f"Keep-alive ping notice: {e}")

@app.on_event("startup")
async def startup_event():
    """
    Runs initial ingestion on startup to populate vector store and starts keep-alive worker.
    """
    logger.info("Application starting up... running initial ingestion job.")
    try:
        run_ingestion_pipeline()
    except Exception as e:
        logger.error(f"Startup ingestion failed: {e}")
        
    # Start 24/7 keep-alive worker
    asyncio.create_task(keep_alive_background_worker())


@app.get("/api/health")
def health_check():
    """
    Returns system status, active sessions, CRM stats, and vector index metrics.
    """
    crm_stats = get_crm_stats()
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "healthy",
        "active_sessions": memory_manager.get_active_sessions_count(),
        "total_crm_customers": crm_stats.get("total_customers", 0),
        "indexed_vectors": len(_LOCAL_VECTOR_STORE),
        "gemini_api_configured": True
    }

@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    """
    Streams conversational responses with real-time SSE tokens, citations, and model intent.
    """
    def event_generator():
        for event in orchestrator.process_chat_stream(
            user_query=request.query,
            session_id=request.session_id,
            user_id=request.user_id
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/memory", response_model=MemoryInspectResponse)
def inspect_memory(session_id: str = "default_session", user_id: str = "user_default"):
    """
    Returns active short-term session window and long-term user profile.
    """
    short_term_turns = memory_manager.get_context_window(session_id)
    user_profile = get_user_profile(user_id)
    return MemoryInspectResponse(
        session_id=session_id,
        user_id=user_id,
        short_term_turns=short_term_turns,
        user_profile=user_profile
    )

# ==========================================
# ENTERPRISE CRM & CUSTOMER FILTERING APIS
# ==========================================

@app.get("/api/crm/customers")
def get_customers(
    stage: Optional[str] = Query(None, description="Filter by customer stage (New Lead, Browsing, Ready to Order, Existing Customer, Support)"),
    preferred_size: Optional[str] = Query(None, description="Filter by size (XS, S, M, L, XL, XXL, 3XL)"),
    location: Optional[str] = Query(None, description="Filter by Kerala location substring (e.g. Kochi, Calicut)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """
    Filters, searches, and organizes customer profiles across all chat channels.
    """
    customers = list_customers_crm(
        stage=stage,
        preferred_size=preferred_size,
        location=location,
        limit=limit,
        offset=offset
    )
    return {
        "count": len(customers),
        "filters": {"stage": stage, "preferred_size": preferred_size, "location": location},
        "customers": customers
    }

@app.get("/api/crm/customers/{user_id}")
def get_customer_detail(user_id: str):
    """
    Returns full customer dossier, preference memory, and past episodic dialogue history.
    """
    crm_data = get_customer_crm(user_id)
    if not crm_data:
        raise HTTPException(status_code=404, detail=f"Customer '{user_id}' not found in CRM.")
    
    # Fetch recent conversation turns
    turns = memory_manager.get_context_window(user_id)
    crm_data["recent_turns"] = turns
    return crm_data

@app.get("/api/crm/stats")
def get_crm_analytics():
    """
    Returns aggregate CRM metrics: customer counts, stage distribution, and top requested sizes.
    """
    return get_crm_stats()

class TagUpdateRequest(BaseModel):
    tags: List[str]
    notes: Optional[str] = None

@app.post("/api/crm/customers/{user_id}/tag")
def tag_customer(user_id: str, req: TagUpdateRequest):
    """
    Manually or automatically tags a customer and adds CRM sales notes.
    """
    res = upsert_customer_crm(
        user_id=user_id,
        tags=req.tags,
        notes=req.notes
    )
    return {"status": "success", "customer": res}

@app.post("/api/ingest", response_model=IngestionResponse)
def trigger_spark_ingestion(request: IngestionRequest, background_tasks: BackgroundTasks):
    """
    Triggers distributed document ingestion.
    """
    try:
        count = run_ingestion_pipeline(sample_docs=request.documents, export_gcs=request.export_gcs)
        return IngestionResponse(
            status="completed",
            chunks_indexed=count,
            message=f"Successfully indexed {count} document chunks."
        )
    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/memory/consolidate")
def trigger_memory_consolidation():
    """
    Triggers episodic memory consolidation.
    """
    try:
        count = consolidate_user_memories_spark()
        return {"status": "success", "users_consolidated": count}
    except Exception as e:
        logger.error(f"Consolidation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount Frontend static files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

instagram_tester_dir = r"C:\Users\sahil\antigravity\instagram_tester"
if os.path.exists(instagram_tester_dir):
    app.mount("/tester", StaticFiles(directory=instagram_tester_dir, html=True), name="tester")

@app.post("/webhook/instagram-test")
@app.post("/webhook/ed03d435-639b-4018-b0be-829891736771")
@app.post("/webhook-test/ed03d435-639b-4018-b0be-829891736771")
async def instagram_webhook_handler(request: Request):
    """
    Direct endpoint for instagram_tester to test Juvelle bot with Qdrant Cloud RAG,
    Session Lifecycle, and Multi-User Isolation.
    """
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
            chat_input = data.get("chatInput") or data.get("message") or ""
            session_id = data.get("sessionId") or "tester_01"
            user_id = data.get("userId") or session_id
        else:
            form = await request.form()
            chat_input = form.get("chatInput", "")
            session_id = form.get("sessionId", "tester_01")
            user_id = form.get("userId", session_id)
        
        messages = generate_juvelle_response(
            chat_input=chat_input,
            session_id=session_id,
            user_id=user_id
        )
        return {"output": messages}
    except Exception as e:
        logger.error(f"Error handling instagram test webhook: {e}")
        return {"output": ["Thank you for reaching out to Juvelle! Please let us know what top you are looking for."]}

from fastapi import UploadFile, File, Form, WebSocket, WebSocketDisconnect
from core.audio_processor import process_voice_message
from core.live_call_manager import live_call_manager

@app.post("/api/voice-message")
async def handle_voice_message(
    audio: UploadFile = File(...),
    sessionId: str = Form("default_user"),
    userName: Optional[str] = Form(None)
):
    """
    Direct voice message intake:
    Transcribes audio using Gemini Multimodal Audio, queries Qdrant RAG,
    and returns textual response (+ optional TTS voice note).
    """
    try:
        audio_bytes = await audio.read()
        mime_type = audio.content_type or "audio/webm"
        
        result = process_voice_message(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            session_id=sessionId,
            customer_name=userName
        )
        return result
    except Exception as e:
        logger.error(f"Voice message processing failed: {e}")
        return {
            "transcript": "Voice message received",
            "detected_language": "english",
            "reply_text": "Thank you for reaching out to Juvelle! How can I assist you with our Churidar tops today?",
            "audio_data": None,
            "has_audio_reply": False,
            "session_id": sessionId
        }

@app.websocket("/api/live-call/{session_id}")
async def live_call_websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    Full-duplex real-time live audio call endpoint supporting multi-session concurrency.
    """
    session = await live_call_manager.connect(session_id, websocket)
    try:
        while True:
            # Receive either binary audio data or text/JSON control frames
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                audio_bytes = message["bytes"]
                await session.handle_user_audio(audio_bytes, mime_type="audio/webm")
            elif "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                    action = payload.get("action")
                    if action == "hangup" or action == "end_call":
                        break
                    elif action == "ping":
                        await session.send_event("pong", {})
                    elif action == "user_text":
                        # Support hybrid text prompt inside live call
                        text_msg = payload.get("text", "")
                        if text_msg:
                            await session.handle_user_audio(text_msg.encode('utf-8'), mime_type="text/plain")
                except Exception as ex:
                    logger.debug(f"Live call frame parsing notice: {ex}")
    except WebSocketDisconnect:
        logger.info(f"Client disconnected from live call: {session_id}")
    except Exception as e:
        logger.error(f"Live call WebSocket error for {session_id}: {e}")
    finally:
        await live_call_manager.disconnect(session_id)

@app.get("/")
def serve_index():
    index_file = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Gemini Spark Custom MCP Server is running!</h1><p>MCP SSE Endpoint: <code>/mcp/sse</code></p>")

