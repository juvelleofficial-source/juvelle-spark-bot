#!/usr/bin/env python3
"""
Zero-Lag Gemini Spark Bot Scaffolding Engine.
Generates an isolated, production-ready, pure-MCP AI chatbot repository in under 2 seconds.
"""

import os
import sys
import json
import argparse
from typing import Dict, Any

TEMPLATES = {
    "fashion": {
        "niche": "Women's Boutique Fashion",
        "specialty": "Daily & Office Wear Churidar Tops",
        "categories_summary": "Pure cotton daily wear tops (₹399–₹699) and soft rayon office wear tops (₹499–₹899) in sizes S–XXL.",
        "exclusions": "T-shirts, kids wear, sarees, jeans",
        "shipping": "Kerala only via Delhivery (2-3 business days, ₹50 shipping)",
        "ordering": "Screenshot from Instagram posts/highlights sent directly in chat",
        "sample_query": "Do you have cotton tops for office wear?"
    },
    "restaurant": {
        "niche": "Artisan Cafe & Bakery",
        "specialty": "Gourmet Coffee, Fresh Pastries & Sourdough Sandwiches",
        "categories_summary": "Espresso brews (₹150–₹280), fresh pastries (₹120–₹350), and artisan sourdough sandwiches (₹250–₹480).",
        "exclusions": "Alcohol, raw catering bulk orders",
        "shipping": "Dine-in, takeaway, and local delivery within 5km radius",
        "ordering": "Pre-orders via chat or table reservation booking",
        "sample_query": "What are your breakfast hours and do you have vegan pastries?"
    },
    "salon": {
        "niche": "Premium Hair & Beauty Salon",
        "specialty": "Hair Styling, Coloring, Facials & Bridal Makeover",
        "categories_summary": "Hair treatments (₹800–₹3500), organic facials (₹1200–₹4000), bridal packages (₹15000+).",
        "exclusions": "Walk-in without confirmation during peak weekend slots",
        "shipping": "In-salon appointments only",
        "ordering": "Date + time slot booking in chat with confirmation",
        "sample_query": "Can I book a hair coloring slot for this Saturday?"
    },
    "b2b": {
        "niche": "Digital Growth & Software Agency",
        "specialty": "Custom Web Applications, AI Chatbots & Cloud Architecture",
        "categories_summary": "Full-stack development, AI agent integration, and DevOps consulting.",
        "exclusions": "Commodity templates, fixed-price un-scoped projects",
        "shipping": "Global remote delivery",
        "ordering": "Book a 30-minute discovery call or submit project scope",
        "sample_query": "How can you help integrate an AI chatbot with our CRM?"
    }
}

def generate_settings_py(brand_name: str) -> str:
    return f'''import os
from pydantic import BaseModel
from typing import Optional

def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip()
        except Exception:
            pass

_load_env()

class Settings(BaseModel):
    APP_NAME: str = "{brand_name}-Spark-Bot"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    
    QDRANT_URL: Optional[str] = os.getenv("QDRANT_URL")
    QDRANT_API_KEY: Optional[str] = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION_NAME: str = os.getenv("QDRANT_COLLECTION_NAME", "{brand_name.lower().replace(' ', '_')}_knowledge")
    
    MEMORY_WINDOW_SIZE: int = 10
    MEMORY_TTL_SECONDS: int = 86400

settings = Settings()
'''

def generate_brand_profile_py(brand_name: str, template_key: str) -> str:
    t = TEMPLATES.get(template_key, TEMPLATES["fashion"])
    return f'''"""
Brand Profile & Business Knowledge Configuration for {brand_name}.
"""

BRAND_PROFILE = {{
    "brand_name": "{brand_name}",
    "business_niche": "{t['niche']}",
    "primary_specialty": "{t['specialty']}",
    "offerings_summary": "{t['categories_summary']}",
    "exclusions": "{t['exclusions']}",
    "shipping_or_location": "{t['shipping']}",
    "ordering_flow": "{t['ordering']}",
    "greetings": {{
        "english": {{
            "first_contact": "Hey there! Welcome to {brand_name}. We specialize in {t['specialty']}. How can I help you today?",
            "returning_customer": "Hey again! Welcome back to {brand_name}. How can I help you today?",
            "mid_chat_checkin": "Hey! Yes, tell me, how can I help you today?"
        }}
    }}
}}
'''

def generate_agent_py(brand_name: str, template_key: str) -> str:
    t = TEMPLATES.get(template_key, TEMPLATES["fashion"])
    return f'''import os
import re
import logging
from typing import List, Dict, Any, Optional
from mcp_server.message_queue import enqueue_facebook_message, mark_message_replied
from retrieval.vector_retriever import retrieve_hybrid_context
from memory.short_term_memory import memory_manager
from memory.customer_profiler import analyze_and_profile_customer
from config.brand_profile import BRAND_PROFILE
from google import genai

logger = logging.getLogger("{brand_name}Agent")

CANDIDATE_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash"
]

GREETING_WORDS = {{"hi", "hello", "hey", "hai", "good morning", "good evening"}}

def get_genai_client() -> Optional[genai.Client]:
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    return None

SYSTEM_PROMPT = """You are the friendly, professional, and helpful Customer Support AI for {brand_name}.

# Core Behavioral Guidelines:
1. Be Concise & Direct: Keep replies to 1-2 crisp sentences.
2. Zero Emoji Default: Do not spam decorative emojis. Use clean punctuation.
3. Direct Answers: Provide immediate answers regarding {t['specialty']} ({t['categories_summary']}).
4. Pacing: Do not interrogate the user with back-to-back question loops.

# Brand Facts:
- Business: {brand_name} ({t['niche']})
- Specialty: {t['specialty']}
- Exclusions: {t['exclusions']}
- Delivery / Location: {t['shipping']}
- Ordering / Booking: {t['ordering']}
"""

def generate_live_reply(
    chat_input: str,
    history: List[Dict[str, Any]],
    lifecycle_info: Optional[Dict[str, Any]] = None,
    crm_profile: Optional[Dict[str, Any]] = None
) -> str:
    state = lifecycle_info.get("lifecycle_state", "first_contact") if lifecycle_info else "first_contact"
    cleaned = chat_input.lower().strip().rstrip("!.,? ")
    
    if state == "active_ongoing" and cleaned in GREETING_WORDS:
        return BRAND_PROFILE["greetings"]["english"]["mid_chat_checkin"]

    retrieved = retrieve_hybrid_context(chat_input, top_k=2)
    rag_context = "\\nRelevant Brand Knowledge:\\n" + "\\n".join([f"- {{c['content']}}" for c in retrieved]) if retrieved else ""

    if state == "first_contact":
        lifecycle_directive = "SESSION DIRECTIVE: First contact turn. Greet warmly and introduce the brand."
    elif state == "returning_session":
        lifecycle_directive = "SESSION DIRECTIVE: Returning customer. Welcome them back warmly."
    else:
        lifecycle_directive = "SESSION DIRECTIVE: Active ongoing conversation. Jump straight into answering."

    prompt = f"{{SYSTEM_PROMPT}}\\n{{lifecycle_directive}}\\n{{rag_context}}\\n\\nCustomer: {{chat_input}}\\nAI:"

    client = get_genai_client()
    if client:
        for model in CANDIDATE_MODELS:
            try:
                resp = client.models.generate_content(model=model, contents=prompt)
                if resp.text:
                    cleaned_text = re.sub(r'[\\u2728\\U0001F338\\U0001F4AB]+', '', resp.text.strip())
                    return cleaned_text
            except Exception:
                continue

    if state == "first_contact":
        return BRAND_PROFILE["greetings"]["english"]["first_contact"]
    return "How can I help you today?"

def generate_response(chat_input: str, session_id: str = "default_user") -> List[str]:
    lifecycle = memory_manager.evaluate_session_lifecycle(session_id, session_id)
    crm = analyze_and_profile_customer(session_id, chat_input)
    msg_id = enqueue_facebook_message(sender_id=session_id, message_text=chat_input)
    history = memory_manager.get_context_window(session_id)
    
    memory_manager.add_turn(session_id, session_id, "user", chat_input)
    reply = generate_live_reply(chat_input, history, lifecycle, crm)
    mark_message_replied(msg_id, reply)
    memory_manager.add_turn(session_id, session_id, "assistant", reply)
    
    return [reply]
'''

def scaffold_project(target_dir: str, brand_name: str, template_key: str = "fashion") -> None:
    """Scaffolds a clean, production-ready AI bot repository."""
    os.makedirs(target_dir, exist_ok=True)
    for sub in ["api", "config", "core", "data", "frontend", "ingestion", "mcp_server", "memory", "retrieval", "tests"]:
        os.makedirs(os.path.join(target_dir, sub), exist_ok=True)

    # 1. Config
    with open(os.path.join(target_dir, "config", "settings.py"), "w", encoding="utf-8") as f:
        f.write(generate_settings_py(brand_name))
    with open(os.path.join(target_dir, "config", "brand_profile.py"), "w", encoding="utf-8") as f:
        f.write(generate_brand_profile_py(brand_name, template_key))
    with open(os.path.join(target_dir, "config", "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")

    # 2. Core
    with open(os.path.join(target_dir, "core", "agent.py"), "w", encoding="utf-8") as f:
        f.write(generate_agent_py(brand_name, template_key))
    with open(os.path.join(target_dir, "core", "__init__.py"), "w", encoding="utf-8") as f:
        f.write("from core.agent import generate_response\n")

    # 3. Environment & Dependencies
    with open(os.path.join(target_dir, ".env.example"), "w", encoding="utf-8") as f:
        f.write(f'''# Environment Configuration for {brand_name}
PORT=8000
HOST=0.0.0.0
GEMINI_API_KEY=your_gemini_api_key_here
QDRANT_URL=https://your-qdrant-cluster.cloud.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key_here
QDRANT_COLLECTION_NAME={brand_name.lower().replace(' ', '_')}_knowledge
''')

    with open(os.path.join(target_dir, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write('''fastapi>=0.110.0
uvicorn>=0.29.0
pydantic>=2.7.0
google-genai>=0.1.1
qdrant-client>=1.9.0
sentence-transformers>=2.7.0
sse-starlette>=2.1.0
requests>=2.31.0
python-multipart>=0.0.9
''')

    # 4. Deployment Files
    with open(os.path.join(target_dir, "Procfile"), "w", encoding="utf-8") as f:
        f.write("web: python start.py\n")

    with open(os.path.join(target_dir, "Dockerfile"), "w", encoding="utf-8") as f:
        f.write('''FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "start.py"]
''')

    with open(os.path.join(target_dir, "start.py"), "w", encoding="utf-8") as f:
        f.write('''import os
import uvicorn
from api.main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
''')

    # 5. README
    with open(os.path.join(target_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(f'''# {brand_name} AI Agent (Gemini Spark MCP)

Autonomous customer support AI for **{brand_name}**, built on the Gemini Spark Model Context Protocol (MCP) architecture.

## Quick Start
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure .env
cp .env.example .env

# 3. Run server
python start.py
```
''')

    print(f"[SUCCESS] Scaffolding complete for '{brand_name}' ({template_key}) at: {target_dir}")

def main():
    parser = argparse.ArgumentParser(description="Scaffold a new Gemini Spark MCP AI Bot")
    parser.add_argument("--name", type=str, default="DemoBrand", help="Brand/Business Name")
    parser.add_argument("--niche", type=str, default="fashion", choices=["fashion", "restaurant", "salon", "b2b"], help="Business Template")
    parser.add_argument("--out", type=str, default="./scaffolded_bot", help="Output directory")

    args = parser.parse_args()
    scaffold_project(args.out, args.name, args.niche)

if __name__ == "__main__":
    main()
