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

GREETING_WORDS = {
    "hi", "hello", "hey", "hai", "helo", "hlo", "haii", "hii", "hiii",
    "yo", "good morning", "good evening", "good afternoon"
}

MANGLISH_INDICATORS = {
    "undu", "undo", "aanu", "aano", "alla", "allathe", "enthaanu", "enthanu", "enthokke", "enthokkeya",
    "kanikku", "kaanikku", "kaanikkatte", "kanikkatte", "ethraya", "ethra", "nokkunnath", "nokkunath",
    "nokkatte", "nokkoo", "cheyyatte", "cheyyam", "cheyyuka", "cheythal", "parayuu", "parayu", "athe",
    "illa", "alle", "kootuthal", "keralathil", "evide", "ivide", "engane", "enganeya", "vellom", "onnum",
    "matte", "ithu", "athu", "njan", "nammal", "nammude", "ningal", "valare", "ippol", "eppo", "vannu",
    "vannilla", "kittumo", "kittum", "venam", "venda", "sahayam", "tharam", "ayakkanam", "ayakkamo",
    "nalla", "ishtam", "undallo", "undath", "cheytholu", "nokkikoloo", "evideya", "aayitt", "ariyatte",
    "ariyamo", "manasilayi", "onnumilla", "kurti", "churithar", "churidhar"
}

def detect_query_language(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    preferred_language: Optional[str] = None
) -> str:
    """
    Deterministically detects whether the customer is speaking in English, Manglish, or Malayalam Script.
    Prevents English messages from mistakenly switching into Manglish mode.
    """
    if not message or not message.strip():
        return preferred_language or "english"

    msg_clean = message.lower().strip()

    # 1. Malayalam Unicode Script Detection
    malayalam_chars = len(re.findall(r'[\u0D00-\u0D7F]', message))
    if malayalam_chars >= 2:
        return "malayalam_script"

    words = set(re.findall(r'[a-zA-Z]+', msg_clean))

    # 2. Check for explicit Manglish indicator words
    manglish_keywords = words.intersection(MANGLISH_INDICATORS)
    if manglish_keywords:
        # If the only match is 'churithar'/'churidhar'/'kurti' and clear English words exist (e.g. "churithars only?"), classify as English
        if manglish_keywords.issubset({"churithar", "churidhar", "kurti"}) and words.intersection({"only", "for", "do", "you", "u", "have", "is", "are", "what", "show", "me", "how", "much", "needed", "need", "nephew", "t-shirt", "shirt"}):
            return "english"
        return "manglish"

    # 3. Check for neutral / single-word tokens ("hi", "hello", "hey", "ok", "yes", "no", "sure", "fine")
    neutral_tokens = {"hi", "hello", "hey", "hai", "helo", "hlo", "ok", "okay", "yes", "no", "sure", "fine", "cool", "done", "kk", "thanks", "thank"}
    if words.issubset(neutral_tokens) or not words:
        if preferred_language in ["english", "manglish", "malayalam_script"]:
            return preferred_language
        if history:
            for turn in reversed(history):
                if turn.get("role") == "user":
                    past_lang = detect_query_language(turn.get("content", ""))
                    if past_lang in ["english", "manglish", "malayalam_script"]:
                        return past_lang
        return "english"

    # 4. Default to English
    return "english"

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
1. Be Concise & Direct: Keep replies to 1-2 crisp sentences. Provide immediate answers with product details and prices.
2. Zero Emoji Default: Do NOT spam emojis (such as ✨, 🌸, etc.). Use standard clean punctuation. Only use an emoji on rare occasions if critical for clarity or warmth.
3. Natural Conversational Tone: Talk like a polite, professional sales coordinator on Instagram DMs. Avoid textbook, stiff, or robotic phrasing.
4. Full Conversation Memory: You have complete access to the ongoing chat history. Always remember and acknowledge any information the customer shares (such as their name, size, location, or style preferences). Never claim you do not have access to details they shared with you in this conversation!
5. Natural Interaction: If the customer asks you to repeat their name or say something friendly (e.g. 'say sahil', 'my name is?'), respond pleasantly and directly (e.g. 'Haha, sure, Sahil! How can I help you with our Churidar tops today?').

# Session & Greeting Lifecycle Rules:
- FIRST CONTACT (New customer turn 1):
  - If the customer introduces their name (e.g., "am sahil and u?", "hi I am Sneha"):
    - English: "Hey [Name]! Welcome to Juvelle. I am Juvelle's customer support assistant. How can I help you today?"
    - Manglish: "Hey [Name]! Welcome to Juvelle. Njan Juvelle inte customer support assistant aanu. Enganeya help cheyyendath?"
  - If generic hello:
    - English Customer: "Hey there! Welcome to Juvelle. We specialize in daily and office wear Churidar tops. How can I help you today?"
    - Manglish Customer: "Hey there! Welcome to Juvelle. Nammal daily and office wear Churidar topsil specialize cheyyunnu. Enganeya help cheyyendath?"
- RETURNING CUSTOMER (Resuming conversation after inactivity > 3 hours):
  - English Customer: "Hey again! Welcome back to Juvelle. How can I help you today?"
  - Manglish Customer: "Hey again! Welcome back to Juvelle. Enganeya help cheyyendath?"
- ACTIVE ONGOING CONVERSATION (< 3 hours since last message): NEVER repeat "Welcome to Juvelle" or deliver a company intro! Jump straight into answering their question directly.
  - If English customer says "hi/hello": "Hey! Yes, tell me, how can I help you today?"
  - If Manglish customer says "hi/hai": "Hey! Parayuu, enganeya help cheyyendathu?"

# Image & Catalog Rules (STRICT & CRITICAL):
- Image/photo sending is NOT currently available in this chat.
- NEVER ask the customer "photo send cheyyatte?" or offer to send photos/images!
- If a customer asks to see designs/photos/collections (e.g., "kanikku", "show me photos", "images undo", "designs kanikku"):
  - English: "You can view our latest daily wear pure cotton and office wear soft rayon tops (₹399–₹899, sizes S–XXL) on our Instagram page posts and highlights. Please send a screenshot of any top you like here to place your order!"
  - Manglish: "Nammalude pure breathable cotton daily wear and soft rayon office wear Churidar tops (₹399 muthal ₹899 vare, sizes S to XXL) Instagram page posts and highlightsil kaanaam. Ishtappetta top inte screenshot ivide send cheythaal order cheyyaam!"

# Audio & Voice Message Perception Rules (CRITICAL):
- You HAVE FULL capability to listen to and process customer voice notes and audio messages directly in this chat.
- If a customer asks if you can hear them, understand audio, or listen to voice notes (e.g., "can you hear me?", "voice note kekkumo?", "can i send audio?", "can u hear audio messages?"):
  - English: "Yes! I can hear and understand your voice messages. Feel free to send voice notes or type here, and I'll assist you with our Churidar tops."
  - Manglish: "Athe! Enikku voice notes kett manasilakkan pattum. Voice message aayitto type cheytho parayaam, njan help cheyyaam."
  - Malayalam: "അതെ! എനിക്ക് വോയ്സ് മെസ്സേജുകൾ കേൾക്കാനും മനസ്സിലാക്കാനും സാധിക്കും. നിങ്ങൾക് വോയ്സ് ആയോ ടൈപ്പ് ചെയ്തോ ചോദിക്കാം."
- NEVER claim "this chat is text-only" or "I cannot hear audio"!

# Conversation Pacing & Direct Answers (STRICT):
- Do NOT interrogate the customer with multiple back-to-back qualifying questions (e.g. "cotton or rayon?", "which color?", "daily or office?").
- When a customer asks for a category (like daily wear), immediately share the product details, fabric, and price range, and explain how to order.
- Ask at most ONE simple closing question only when strictly necessary (e.g. "Which size are you looking for?" / "Ethu size aanu nokkunnath?").

# Strict Language Mirroring & Manglish Rules (CRITICAL):
- STRICT LANGUAGE LOCK:
  - When the customer speaks in English (e.g. "i need a t shirt", "churithars only?", "what is the price?"), you MUST reply in 100% fluent, professional English. NEVER switch to Manglish or Malayalam!
  - When the customer speaks in Manglish (e.g. "kanikku", "rate ethraya", "keralathil delivery undo"), reply in natural Manglish.
  - When the customer speaks in Malayalam script, reply in clean Malayalam script.
- MANGLISH PURITY (When responding in Manglish):
  - Use ONLY 100% English alphabet letters. NEVER mix Malayalam script characters (e.g. ക്കേണ്ട, ്, ം) inside English words.
  - NO HYPHENS (-): Real humans never type hyphens attached to words in chat.
    - WRONG: Juvelle-te, Kerala-il, delivery-kku, order-inte, brand-nte, available-aanu
    - RIGHT: Juvelle inte, Kerala yil (or Keralathil), deliverykku, order cheyyan, brand inte, available aanu
  - POSSESSIVE: Always use 'inte' (e.g. "Juvelle inte"), NEVER use "-te" or "Juvelle-te".

# Brand Facts:
- Specialty: Exclusively women's Churidar tops (pure cotton & soft rayon blends, ₹399 to ₹899, sizes S to XXL).
- Exclusions: No sarees, frocks, jeans, t-shirts, kids wear, or men's wear.
- Shipping: KERALA ONLY via Delhivery (2-3 business days, ₹50 standard shipping). Orders outside Kerala are politely declined.
- Ordering & Payment: Direct chat ordering (screenshot from Instagram page + size). 100% online advance payment (UPI/GPay/PhonePe/Bank Transfer). No Cash on Delivery (COD).
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

def sanitize_manglish_response(text: str, target_language: str = "manglish") -> str:
    """
    Post-processes and cleans responses to eliminate character leakage,
    remove unnatural hyphens, strip emoji spam, and enforce natural human phrasing.
    """
    if not text:
        return text

    # 1. Strip unwanted decorative emoji spam (e.g. ✨, 🌸, 💫, 🌟)
    text = re.sub(r'[\u2728\U0001F338\U0001F4AB\U0001F31F\U0001F33C\U0001F389]+', '', text)

    if target_language == "english":
        # For English, just clean up whitespace and hyphens
        text = re.sub(r' +', ' ', text).strip()
        return text

    latin_count = len(re.findall(r'[a-zA-Z]', text))
    malayalam_count = len(re.findall(r'[\u0D00-\u0D7F]', text))

    # 2. Script Bleed Removal: If response is mostly Latin Manglish, fix any rogue Malayalam unicode
    if latin_count > 0 and latin_count >= malayalam_count:
        for mal_char, eng_rep in sorted(MALAYALAM_UNICODE_MAP.items(), key=lambda x: len(x[0]), reverse=True):
            text = text.replace(mal_char, eng_rep)
        # Strip any lingering unmapped unicode chars
        text = re.sub(r'[\u0D00-\u0D7F]', '', text)

    # 3. Fix unnatural hyphens
    text = re.sub(r'\b([A-Za-z]+)-(te|nte|inte)\b', r'\1 inte', text, flags=re.IGNORECASE)
    text = re.sub(r'\bKerala-il\b', 'Kerala yil', text, flags=re.IGNORECASE)
    text = re.sub(r'\b([A-Za-z]+)-(il|yil)\b', r'\1 il', text, flags=re.IGNORECASE)
    text = re.sub(r'\b([A-Za-z]+)-(kku|ku)\b', r'\1kku', text, flags=re.IGNORECASE)
    text = re.sub(r'\b([A-Za-z]+)-(anu|aanu|alla)\b', r'\1 \2', text, flags=re.IGNORECASE)
    text = re.sub(r'([A-Za-z]{2,})-([A-Za-z]{2,})', r'\1 \2', text)

    # 4. Clean up double spaces or awkward punctuation
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
    customer CRM context, strict language mirroring, candidate cascade, and RAG grounding.
    """
    # 1. Detect language
    detected_lang = detect_query_language(
        message=chat_input,
        history=history,
        preferred_language=crm_profile.get("preferred_language") if crm_profile else None
    )

    state = lifecycle_info.get("lifecycle_state", "first_contact") if lifecycle_info else "first_contact"
    turn_num = lifecycle_info.get("turn_count", 1) if lifecycle_info else 1
    cleaned_input = chat_input.lower().strip().rstrip("!.,? ")

    # 2. Check for mid-conversation casual greeting intercept
    if state == "active_ongoing" and cleaned_input in GREETING_WORDS:
        if detected_lang == "manglish":
            return "Hey! Parayuu, enganeya help cheyyendathu?"
        elif detected_lang == "malayalam_script":
            return "ഹലോ! പറയൂ, എങ്ങനെയാണ് സഹായിക്കേണ്ടത്?"
        return "Hey! Yes, tell me, how can I help you today?"

    # 3. Retrieve grounded knowledge chunks from Qdrant Cloud / BM25
    retrieved_chunks = retrieve_hybrid_context(chat_input, top_k=2)
    rag_context = ""
    if retrieved_chunks:
        rag_context = "\nRelevant Juvelle Brand Knowledge:\n" + "\n".join([f"- {c['content']}" for c in retrieved_chunks])

    # 4. Formulate Strict Language Directive
    if detected_lang == "english":
        lang_directive = (
            "CRITICAL LANGUAGE ENFORCEMENT: The customer is speaking in ENGLISH. "
            "You MUST reply in 100% fluent, natural ENGLISH. "
            "DO NOT use ANY Malayalam or Manglish words (such as 'Athe', 'nammalude', 'undo', 'aanu', 'parayuu', 'kaanikku')."
        )
    elif detected_lang == "malayalam_script":
        lang_directive = (
            "CRITICAL LANGUAGE ENFORCEMENT: The customer is typing in MALAYALAM SCRIPT. "
            "You MUST reply in clean, grammatically correct MALAYALAM SCRIPT only."
        )
    else:
        lang_directive = (
            "CRITICAL LANGUAGE ENFORCEMENT: The customer is speaking in MANGLISH (Malayalam in English letters). "
            "Reply in natural, polite Manglish without hyphens or Malayalam Unicode script bleed."
        )

    # 5. Formulate Session Lifecycle & Greeting Directive
    if state == "first_contact":
        if detected_lang == "english":
            lifecycle_directive = (
                "SESSION DIRECTIVE: FIRST CONTACT (Turn 1). Greet warmly in English and introduce the brand: "
                "'Hey there! Welcome to Juvelle. We specialize in daily and office wear Churidar tops. How can I help you today?'"
            )
        else:
            lifecycle_directive = (
                "SESSION DIRECTIVE: FIRST CONTACT (Turn 1). Greet warmly in Manglish and introduce the brand: "
                "'Hey there! Welcome to Juvelle. Nammal daily and office wear Churidar topsil specialize cheyyunnu. Enganeya help cheyyendath?'"
            )
    elif state == "returning_session":
        crm_size = crm_profile.get("preferred_size") if crm_profile else None
        size_hint = f" (Customer previously looked for size {crm_size})" if crm_size else ""
        if detected_lang == "english":
            lifecycle_directive = (
                f"SESSION DIRECTIVE: RETURNING CUSTOMER (Resuming after > 3 hrs inactivity){size_hint}. "
                "Start your reply in English by welcoming them back warmly: 'Welcome back to Juvelle! How can I help you today?' before answering."
            )
        else:
            lifecycle_directive = (
                f"SESSION DIRECTIVE: RETURNING CUSTOMER (Resuming after > 3 hrs inactivity){size_hint}. "
                "Start your reply in Manglish by welcoming them back warmly: 'Welcome back to Juvelle! Enganeya help cheyyendath?' before answering."
            )
    else:
        lifecycle_directive = (
            f"SESSION DIRECTIVE: ACTIVE ONGOING CONVERSATION (Turn {turn_num}, < 3 hrs since last message). "
            "DO NOT repeat 'Welcome to Juvelle' or deliver a brand intro! Jump straight into answering their question naturally and directly."
        )

    # 6. CRM Context Snippet
    crm_context = ""
    if crm_profile and (crm_profile.get("preferred_size") or crm_profile.get("location") or crm_profile.get("stage")):
        crm_context = f"\nCustomer CRM Profile: Size={crm_profile.get('preferred_size', 'Unknown')}, Location={crm_profile.get('location', 'Unknown')}, Stage={crm_profile.get('stage', 'New Lead')}, Language={detected_lang}\n"

    # 7. Build conversation prompt
    dialogue_history = ""
    if history:
        for turn in history[-4:]:
            role = "Customer" if turn.get("role") == "user" else "Juvelle AI"
            dialogue_history += f"{role}: {turn.get('content', '')}\n"

    full_prompt = (
        f"{JUVELLE_SYSTEM_PROMPT}\n\n"
        f"{lang_directive}\n\n"
        f"{lifecycle_directive}\n"
        f"{crm_context}"
        f"{rag_context}\n\n"
        f"Conversation History:\n{dialogue_history}"
        f"Customer: {chat_input}\n"
        f"Juvelle AI:"
    )

    # 8. Call candidate neural models with rapid cascade
    client = get_genai_client()
    if client:
        for model_name in CANDIDATE_MODELS:
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=full_prompt
                )
                if resp.text:
                    cleaned_reply = sanitize_manglish_response(resp.text.strip(), target_language=detected_lang)
                    return cleaned_reply
            except Exception as e:
                logger.warning(f"Model {model_name} attempt error: {e}")
                continue

    # Intelligent fallback handling based on query intent & language
    cleaned_lower = chat_input.lower().strip()
    is_greeting_only = cleaned_lower in GREETING_WORDS or len(cleaned_lower.split()) <= 2 and any(w in cleaned_lower for w in GREETING_WORDS)
    
    if any(w in cleaned_lower for w in ["cash", "money", "loan", "borrow", "fund"]):
        if detected_lang == "english":
            return "I am Juvelle's fashion assistant and can only help you with our daily and office wear Churidar tops! How can I help you today?"
        return "Njan Juvelle fashion assistant aanu, Churidar tops purchase cheyyan mathre help cheyyan pattu. Collections kaanikkatte?"

    if state == "first_contact" and is_greeting_only:
        if detected_lang == "english":
            return "Hey there! Welcome to Juvelle. We specialize in daily and office wear Churidar tops. How can I help you today?"
        return "Hey there! Welcome to Juvelle. Nammal daily and office wear Churidar topsil specialize cheyyunnu. Enganeya help cheyyendath?"
    elif state == "returning_session" and is_greeting_only:
        if detected_lang == "english":
            return "Welcome back to Juvelle! How can I assist you today?"
        return "Welcome back to Juvelle! Enganeya help cheyyendath?"
    
    if detected_lang == "english":
        return "We specialize exclusively in women's Churidar tops (₹399–₹899). How can I help you with our collection today?"
    return "Nammal women's Churidar topsil (₹399–₹899) aanu specialize cheyyunnath. Enganeya help cheyyendath?"

def generate_juvelle_response(
    chat_input: str,
    session_id: str = "default_tester",
    user_id: Optional[str] = None
) -> List[str]:
    """
    Processes customer messages with full Session Lifecycle Management, Multi-User Isolation,
    Automated CRM Profiling, Strict Language Locking, and Real Neural AI generation.
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

def generate_juvelle_reply(
    customer_message: str,
    session_id: str = "default_tester",
    customer_name: Optional[str] = None
) -> str:
    """
    Convenience wrapper returning a single clean string response for voice notes and live calls.
    """
    msgs = generate_juvelle_response(
        chat_input=customer_message,
        session_id=session_id,
        user_id=customer_name or session_id
    )
    return " ".join(msgs)

