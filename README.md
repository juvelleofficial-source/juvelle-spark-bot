# Gemini + Apache Spark Enterprise RAG Chatbot (100% Free / Zero-Cost)

A production-grade, enterprise-ready custom conversational AI chatbot combining **Google Gemini** for generative reasoning and **Apache Spark (PySpark)** for distributed document ingestion, token-aware chunking, batch vector embeddings, and multi-tier memory consolidation.

---

## 🌟 Key Highlights & Zero-Cost Architecture

- **100% Free**: Operates entirely on your local machine using local PySpark (`local[*]`), local vector indexing, local SQLite dual-tier memory, and Google AI Studio's perpetual Free Tier API.
- **Distributed Apache Spark Ingestion**: Token-aware semantic chunking with sliding context overlap distributed across local CPU cores.
- **Hybrid Vector Retrieval**: Dense vector similarity search fused with BM25 keyword matching via Reciprocal Rank Fusion (RRF).
- **Dual-Tier Memory Architecture**:
  - **Short-Term Memory**: Sub-millisecond in-memory RAM cache with automatic sliding-window truncation.
  - **Long-Term Memory**: Persistent local SQLite database (`data/memory.db`) storing full conversational transcripts.
  - **Spark Memory Consolidation**: Scheduled PySpark batch jobs that analyze user dialogue patterns and synthesize long-term user profile summaries.
- **Dynamic Model Routing**: Routes routine factual queries to **Gemini 1.5/2.0 Flash** and complex multi-step reasoning to **Gemini Pro**.
- **Modern Glassmorphism Web App**: Real-time token streaming, live citation inspector, memory visualizer, and on-demand Spark job execution.

---

## 📁 Project Structure

```
├── api/
│   ├── main.py                   # FastAPI ASGI server with SSE streaming & REST routes
│   └── schemas.py                # Pydantic request and response schemas
├── config/
│   └── settings.py               # Pydantic environment configurations
├── core/
│   ├── gemini_client.py          # Google AI Studio Free Tier client with offline fallback
│   ├── router.py                 # Query intent & model tier router
│   └── orchestrator.py           # End-to-end RAG, memory & streaming orchestrator
├── data/                         # Persistent local SQLite memory database & documents
├── frontend/
│   ├── index.html                # Modern glassmorphism web user interface
│   ├── style.css                 # Dark-mode styling, glowing badges & animations
│   └── app.js                    # SSE stream consumer, markdown parser & UI handlers
├── ingestion/
│   ├── spark_session.py          # Optimized Apache Spark session builder
│   ├── document_processor.py     # Distributed chunking and metadata extractor
│   ├── batch_embedder.py         # Batch embedding generator with rate limiters
│   ├── vector_indexer.py         # In-memory & local vector indexer
│   └── ingestion_job.py          # End-to-end Spark ETL pipeline script
├── memory/
│   ├── short_term_memory.py      # Sub-1ms working window memory manager
│   ├── long_term_memory.py       # SQLite episodic conversation & profile store
│   └── spark_memory_consolidator.py # Spark batch memory clustering & consolidation
├── tests/
│   └── test_system.py            # Complete PyTest suite
├── requirements.txt              # Project dependencies
└── README.md
```

---

## 🚀 Getting Started

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. (Optional) Set Your Google AI Studio Free API Key

Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your_free_google_ai_studio_api_key
```
*(Note: If no API key is set, the system automatically runs in **Offline Local Demo Mode** with simulated streaming and full Spark RAG retrieval).*

### 3. Run the Apache Spark Ingestion Job

```bash
python ingestion/ingestion_job.py
```

### 4. Launch the FastAPI Server & Web App

```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser and navigate to: **`http://localhost:8000`**

---

## 🧪 Running Tests

```bash
pytest tests/test_system.py -v
```
