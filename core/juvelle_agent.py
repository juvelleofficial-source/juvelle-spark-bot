import os
import re
import logging
from typing import List, Dict, Any, Optional
from mcp_server.message_queue import enqueue_facebook_message, mark_message_replied
from retrieval.vector_retriever import retrieve_hybrid_context
from memory.short_term_memory import memory_manager
from memory.customer_profiler import analyze_and_profile_customer
from memory.long_term_memory import get_customer_crm
from google import genai

logger = logging.getLogger("JuvelleAgent")

CANDIDATE_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.5-flash"
]

def get_genai_client() -> Optional[genai.Client]:
    """Dynamically resolves and returns an authenticated Google GenAI client."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY="):
                            api_key = line.split("=", 1)[1].strip()
                            os.environ["GEMINI_API_KEY"] = api_key
                            break
            except Exception:
                pass
    if api_key:
        return genai.Client(api_key=api_key)
    return None

JUVELLE_SYSTEM_PROMPT = """You are the friendly, professional, and helpful Customer Support AI for Juvelle, a boutique women's fashion brand in Kerala.

# Core Behavioral Guidelines:
1. Be Concise & Human: Keep replies to 1-2 crisp sentences. Do NOT dump long paragraphs or unnecessary information.
2. Emoji Restraint: Use at most 0 to 1 subtle emoji (e.g. ✨ or 🌸). Never spam emojis.
3. Natural Conversational Tone: Talk like a polite, modern sales coordinator on Instagram DMs. Avoid textbook, stiff, or robotic phrasing.

# Session & Greeting Lifecycle Rules:
- FIRST CONTACT (New customer turn 1): Give a warm, branded introductory welcome (e.g., "Hey there! Welcome to Juvelle 🌸 We specialize in daily & office wear Churidar tops. How can I help you today? ✨").
- RETURNING CUSTOMER (Resuming conversation after inactivity > 30 mins): Give a warm re-engagement greeting (e.g., "Hey again! Welcome back to Juvelle ✨ How can I help you today?").
- ACTIVE ONGOING CONVERSATION (< 30 mins since last message): NEVER repeat "Welcome to Juvelle" or deliver a company intro! Answer the customer's specific question directly and politely. If the customer just says "hi/hey" mid-chat, give a quick casual reply (e.g., "Hey! Yes, tell me? ✨" or "Hey! Enthaanu nokkunnath? ✨").

# Strict Manglish & Language Rules (CRITICAL):
- PURE SCRIPT ONLY: When speaking in Manglish (Malayalam in English letters), use ONLY 100% English alphabet letters. NEVER mix Malayalam script characters (e.g. േണ്ട, ്, ം) inside English words.
- NO HYPHENS (-): Real humans never type hyphens attached to words in chat.
  - WRONG: Juvelle-te, Kerala-il, delivery-kku, order-inte, brand-nte, available-aanu
  - RIGHT: Juvelle inte, Kerala yil (or Keralathil), deliverykku, order cheyyan, brand inte, available aanu
- POSSESSIVE: Always use 'inte' (e.g. "Juvelle inte"), NEVER use "-te" or "Juvelle-te".
- NATURAL HUMAN PHRASING:
  - Instead of robotic "Enikku enthu sahayam aanu cheyyendathu?", use natural phrasing like "Enthaanu nokkunnath? ✨", "Enganeya help cheyyendath? ✨", or "Enthelum models kaanikkatte? ✨".
  - If asked if you are a human/owner (e.g., "sahil aano?"): "Illa, njan Juvelle inte AI assistant aanu! Enthaanu nokkunnath? ✨"

# Language Mirroring:
- Manglish Customer -> Natural, polite Manglish response.
- Malayalam Script Customer -> Pure, clean Malayalam script response.
- English Customer -> Clear, professional English response.

# Brand Facts:
- Specialty: Exclusively women's Churidar tops (pure cotton & soft rayon blends, ₹399 to ₹899).
- Exclusions: No sarees, frocks, jeans, t-shirts, kids wear, or men's wear.
- Shipping: KERALA ONLY via Delhivery (2-3 business days, ₹50 standard shipping). Orders outside Kerala are politely declined.
- Ordering & Payment: Direct chat ordering (screenshot + size). 100% online advance payment (UPI/GPay/PhonePe/Bank Transfer). No Cash on Delivery (COD).
- No Website: Everything is handled directly in chat.
"""

MALAYALAM_UNICODE_MAP = {
    'ക്കേണ്ട': 'kkenda',
    'േണ്ട': 'enda',
    'ണ്ട': 'nda',
    'ത്ത': 'ttha',
    'ച്ച': 'ccha',
    'ല്ല': 'lla',
    'ക്ക': 'kka',
    'ന്ന': 'nna',
    'മ്മ': 'mma',
    'റ്റ': 'tta',
    'ഞ': 'nja',
    'ങ്ങ': 'nga',
    'ാ': 'a',
    'ി': 'i',
    'ീ': 'ee',
    'ു': 'u',
    'ൂ': 'oo',
    'െ': 'e',
    'േ': 'e',
    '്': '',
    'ം': 'm',
    'ൽ': 'l',
    'ർ': 'r',
    'ൻ': 'n',
    'ണ്': 'n',
    'ണ': 'na',
    'ന': 'na',
    'മ': 'ma',
    'യ': 'ya',
    'ര': 'ra',
    'ല': 'la',
    'വ': 'va',
    'ശ': 'sha',
    'ഷ': 'sha',
    'സ': 'sa',
    'ഹ': 'ha',
    'ള': 'la',
    'ഴ': 'zha',
    'റ': 'ra',
    'ക': 'ka',
    'ഗ': 'ga',
    'ച': 'cha',
    'ജ': 'ja',
    'ട': 'ta',
    'ഡ': 'da',
    'ത': 'tha',
    'ദ': 'da',
    'പ': 'pa',
    'ബ': 'ba'
}

def sanitize_manglish_response(text: str) -> str:
    """
    Post-processes and cleans Manglish responses to eliminate character leakage,
    remove unnatural hyphens, and enforce natural human chat phrasing.
    """
    if not text:
        return text

    latin_count = len(re.findall(r'[a-zA-Z]', text))
    malayalam_count = len(re.findall(r'[\u0D00-\u0D7F]', text))

    # 1. Script Bleed Removal: If response is mostly Latin Manglish, fix any rogue Malayalam unicode
    if latin_count > 0 and latin_count >= malayalam_count:
        for mal_char, eng_rep in sorted(MALAYALAM_UNICODE_MAP.items(), key=lambda x: len(x[0]), reverse=True):
            text = text.replace(mal_char, eng_rep)
        # Strip any lingering unmapped unicode chars
        text = re.sub(r'[\u0D00-\u0D7F]', '', text)

    # 2. Fix unnatural hyphens
    # Brand/proper noun possessives: 'Juvelle-te' -> 'Juvelle inte'
    text = re.sub(r'\b([A-Za-z]+)-(te|nte|inte)\b', r'\1 inte', text, flags=re.IGNORECASE)
    # Location/noun locatives: 'Kerala-il' -> 'Kerala yil'
    text = re.sub(r'\bKerala-il\b', 'Kerala yil', text, flags=re.IGNORECASE)
    text = re.sub(r'\b([A-Za-z]+)-(il|yil)\b', r'\1 il', text, flags=re.IGNORECASE)
    # Datives: 'delivery-kku' -> 'deliverykku'
    text = re.sub(r'\b([A-Za-z]+)-(kku|ku)\b', r'\1kku', text, flags=re.IGNORECASE)
    # Verb copulas: 'available-aanu' -> 'available aanu'
    text = re.sub(r'\b([A-Za-z]+)-(anu|aanu|alla)\b', r'\1 \2', text, flags=re.IGNORECASE)
    # Generic mid-word hyphens
    text = re.sub(r'([A-Za-z]{2,})-([A-Za-z]{2,})', r'\1 \2', text)

    # 3. Clean up double spaces or awkward punctuation
    text = re.sub(r' +', ' ', text).strip()
    return text

def generate_live_neural_reply(
    chat_input: str,
    history: List[Dict[str, Any]],
    lifecycle_info: Optional[Dict[str, Any]] = None,
    crm_profile: Optional[Dict[str, Any]] = None
) -> str:
    """
    Executes live neural AI generation using Google Gemini model with session lifecycle guidance,
    customer CRM context, language mirroring, candidate cascade, and RAG grounding.
    """
    # 1. Retrieve grounded knowledge chunks from Qdrant Cloud / BM25
    retrieved_chunks = retrieve_hybrid_context(chat_input, top_k=2)
    rag_context = ""
    if retrieved_chunks:
        rag_context = "\nRelevant Juvelle Brand Knowledge:\n" + "\n".join([f"- {c['content']}" for c in retrieved_chunks])

    # 2. Formulate Session Lifecycle & Greeting Directive
    state = lifecycle_info.get("lifecycle_state", "first_contact") if lifecycle_info else "first_contact"
    turn_num = lifecycle_info.get("turn_count", 1) if lifecycle_info else 1

    if state == "first_contact":
        lifecycle_directive = (
            "SESSION DIRECTIVE: FIRST CONTACT (Turn 1). Greet the customer warmly and introduce the brand "
            "(e.g., 'Hey there! Welcome to Juvelle 🌸 We specialize in daily & office wear Churidar tops. How can I help you today? ✨')."
        )
    elif state == "returning_session":
        crm_size = crm_profile.get("preferred_size") if crm_profile else None
        size_hint = f" (Customer previously looked for size {crm_size})" if crm_size else ""
        lifecycle_directive = (
            f"SESSION DIRECTIVE: RETURNING CUSTOMER (Resuming after > 3 hrs inactivity){size_hint}. "
            "You MUST start your reply by welcoming them back warmly (e.g., 'Welcome back to Juvelle! ✨' or 'Hey again! ✨') before answering their inquiry."
        )
    else:
        lifecycle_directive = (
            f"SESSION DIRECTIVE: ACTIVE ONGOING CONVERSATION (Turn {turn_num}, < 3 hrs since last message). "
            "DO NOT repeat 'Welcome to Juvelle' or give a brand intro! Jump straight into answering their question naturally and directly. "
            "If they say a casual greeting like 'hi/hey', reply briefly like 'Hey! Yes, tell me? ✨'."
        )

    # 3. CRM Context Snippet
    crm_context = ""
    if crm_profile and (crm_profile.get("preferred_size") or crm_profile.get("location") or crm_profile.get("stage")):
        crm_context = f"\nCustomer CRM Profile: Size={crm_profile.get('preferred_size', 'Unknown')}, Location={crm_profile.get('location', 'Unknown')}, Stage={crm_profile.get('stage', 'New Lead')}\n"

    # 4. Build conversation prompt
    dialogue_history = ""
    if history:
        for turn in history[-4:]:
            role = "Customer" if turn.get("role") == "user" else "Juvelle AI"
            dialogue_history += f"{role}: {turn.get('content', '')}\n"

    full_prompt = (
        f"{JUVELLE_SYSTEM_PROMPT}\n"
        f"{lifecycle_directive}\n"
        f"{crm_context}"
        f"{rag_context}\n\n"
        f"Conversation History:\n{dialogue_history}"
        f"Customer: {chat_input}\n"
        f"Juvelle AI:"
    )

    # 5. Call candidate neural models with rapid cascade
    client = get_genai_client()
    if client:
        for model_name in CANDIDATE_MODELS:
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=full_prompt
                )
                if resp.text:
                    cleaned_reply = sanitize_manglish_response(resp.text.strip())
                    return cleaned_reply
            except Exception as e:
                logger.warning(f"Model {model_name} attempt error: {e}")
                continue

    # Fallback based on session lifecycle
    if state == "first_contact":
        return "Hey there! Welcome to Juvelle 🌸 We specialize in daily & office wear Churidar tops. How can I help you today? ✨"
    elif state == "returning_session":
        return "Welcome back to Juvelle! ✨ How can I assist you today?"
    return "Sure! How can I help you find something special today? ✨"

def generate_juvelle_response(
    chat_input: str,
    session_id: str = "default_tester",
    user_id: Optional[str] = None
) -> List[str]:
    """
    Processes customer messages with full Session Lifecycle Management, Multi-User Isolation,
    Automated CRM Profiling, and Real Neural AI generation.
    """
    effective_user_id = user_id or session_id

    # 1. Evaluate Session Lifecycle (First Contact vs Returning vs Active Ongoing)
    lifecycle_info = memory_manager.evaluate_session_lifecycle(session_id, effective_user_id)

    # 2. Automated CRM Attribute & Intent Profiling
    crm_profile = analyze_and_profile_customer(effective_user_id, chat_input)

    # 3. Enqueue inquiry into MCP Inbox
    msg_id = enqueue_facebook_message(
        sender_id=effective_user_id,
        message_text=chat_input,
        sender_name=f"Customer {effective_user_id[:8]}",
        platform="instagram"
    )

    # 4. Retrieve short-term dialogue context
    history = memory_manager.get_context_window(session_id)

    # 5. Record user turn in memory
    try:
        memory_manager.add_turn(
            session_id=session_id,
            user_id=effective_user_id,
            role="user",
            content=chat_input
        )
    except Exception:
        pass

    # 6. Generate concise, session-aware neural response
    ai_reply = generate_live_neural_reply(chat_input, history, lifecycle_info, crm_profile)

    # 7. Mark message as replied in MCP queue
    mark_message_replied(message_id=msg_id, ai_reply=ai_reply)

    # 8. Record assistant turn in short-term memory
    try:
        memory_manager.add_turn(
            session_id=session_id,
            user_id=effective_user_id,
            role="assistant",
            content=ai_reply
        )
    except Exception:
        pass

    # Return concise bubble
    if "\n\n" in ai_reply:
        parts = [msg.strip() for msg in ai_reply.split("\n\n") if msg.strip()]
        return parts[:2]
    return [ai_reply.strip()]
