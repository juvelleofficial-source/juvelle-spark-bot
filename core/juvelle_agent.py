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
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash"
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
    "undallo", "undath", "cheytholu", "nokkikoloo", "evideya", "aayitt", "ariyatte", "ariyamo", "manasilayi",
    "onnumilla", "churithar", "churidhar", "topundo", "vilayethra", "ethrayanu", "rateethraya", "kurtiyundo",
    "namaskaram", "sugamano", "entha", "evidunnu", "kerala", "kochi", "calicut", "kannur", "thrissur", "malappuram",
    "kazhinjo", "varumo", "ayakkumo", "edukkatte", "nokki", "parayam", "vegam", "pathiye", "angane", "ingane"
}

HINGLISH_INDICATORS = {
    "hai", "hain", "kya", "kare", "kaise", "kitna", "kitne", "chahiye", "bhai", "aap", "aapka", "aapke",
    "nahi", "dikhao", "batao", "daam", "kapda", "accha", "achha", "muje", "mujhe", "bhejo",
    "kardo", "milega", "milegi", "hoga", "hogi", "bolo", "bataiye", "paas", "dijiye", "shukriya", "dhanyawad",
    "dekhna", "kharidna", "bhejiye", "pata", "sahi", "dupatta", "kurtiyan", "kab", "tak", "karo", "bhi", "toh"
}

TANGLISH_INDICATORS = {
    "irukka", "irukku", "evvalavu", "sollunga", "pannunga", "enna", "vanganum",
    "kudunga", "theriyuma", "romba", "illai", "solren", "kedaikkuma", "yenna", "panreenga",
    "parunga", "venum", "kodu", "annachi", "engitta", "epdi", "eppadi", "ungalukku", "kudupingala"
}

def detect_query_language(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    preferred_language: Optional[str] = None,
    is_voice: bool = False
) -> str:
    """
    Deterministically detects customer language and script across English, Manglish, Malayalam,
    Hinglish, Hindi, Tanglish, Tamil, Telugu, Kannada, Arabic, and universal polyglot inputs.
    Supports instant turn-by-turn dynamic switching and voice message Latin transliteration defaults.
    """
    if not message or not message.strip():
        return preferred_language or "english"

    msg_clean = message.lower().strip()

    # 1. Unicode Script Detections with character count dominance
    script_counts = {
        "malayalam_script": len(re.findall(r'[\u0D00-\u0D7F]', message)),
        "hindi_script": len(re.findall(r'[\u0900-\u097F]', message)),
        "tamil_script": len(re.findall(r'[\u0B80-\u0BFF]', message)),
        "telugu_script": len(re.findall(r'[\u0C00-\u0C7F]', message)),
        "kannada_script": len(re.findall(r'[\u0C80-\u0CFF]', message)),
        "arabic_script": len(re.findall(r'[\u0600-\u06FF]', message))
    }
    dominant_script, max_count = max(script_counts.items(), key=lambda x: x[1])
    if max_count >= 2:
        if is_voice:
            # Check if customer previously explicitly typed in native script
            prev_had_native_script = False
            if history:
                for turn in reversed(history[-4:]):
                    if turn.get("role") == "user":
                        prev_text = turn.get("content", "")
                        if len(re.findall(r'[ഀ-ൿ]', prev_text)) >= 2:
                            prev_had_native_script = True
                            break
            if not prev_had_native_script:
                # Voice messages default to Latin transliteration for Indian regional languages
                if dominant_script == "malayalam_script":
                    return "manglish"
                elif dominant_script == "hindi_script":
                    return "hinglish"
                elif dominant_script == "tamil_script":
                    return "tanglish"
        return dominant_script

    words = set(re.findall(r'[a-zA-Z]+', msg_clean))

    # Distinctive regional grammar markers (excluding generic geographic names like "kerala")
    manglish_grammar_words = MANGLISH_INDICATORS - {"kerala", "kochi", "calicut", "kannur", "thrissur", "malappuram"}
    manglish_count = len(words.intersection(manglish_grammar_words))
    hinglish_count = len(words.intersection(HINGLISH_INDICATORS))
    tanglish_count = len(words.intersection(TANGLISH_INDICATORS))

    # If clothing terms match but with clear English grammar words
    if manglish_count > 0 and words.intersection(manglish_grammar_words).issubset({"churithar", "churidhar"}):
        if words.intersection({"only", "for", "do", "you", "u", "have", "is", "are", "what", "show", "me", "how", "much", "needed", "need", "nephew", "t-shirt", "shirt"}):
            return "english"

    if max(manglish_count, hinglish_count, tanglish_count) > 0:
        if hinglish_count > manglish_count and hinglish_count >= tanglish_count:
            return "hinglish"
        elif tanglish_count > manglish_count and tanglish_count >= hinglish_count:
            return "tanglish"
        elif manglish_count >= hinglish_count and manglish_count >= tanglish_count:
            return "manglish"

    # Contextual memory inheritance ONLY for ambiguous single-word responses (e.g. "ok", "yes", "s", "m")
    AMBIGUOUS_SHORT_WORDS = {"ok", "okay", "yes", "no", "sure", "fine", "done", "s", "m", "l", "xl", "xxl", "3xl", "hai", "k", "kk"}
    if msg_clean in AMBIGUOUS_SHORT_WORDS and history:
        # Check immediately preceding user turn only (not walking back indefinitely)
        for turn in reversed(history[-2:]):
            if turn.get("role") == "user":
                prev_text = turn.get("content", "")
                if prev_text.lower().strip() != msg_clean:
                    prev_lang = detect_query_language(prev_text, history=None, preferred_language=None, is_voice=is_voice)
                    if prev_lang:
                        return prev_lang

    return "english"

_GENAI_CLIENT_SINGLETON: Optional[genai.Client] = None

def get_genai_client() -> Optional[genai.Client]:
    """Dynamically resolves and returns a cached singleton Google GenAI client."""
    global _GENAI_CLIENT_SINGLETON
    if _GENAI_CLIENT_SINGLETON is not None:
        return _GENAI_CLIENT_SINGLETON

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
        _GENAI_CLIENT_SINGLETON = genai.Client(api_key=api_key)
        return _GENAI_CLIENT_SINGLETON
    return None

JUVELLE_SYSTEM_PROMPT = """You are the friendly, professional, and helpful Customer Support AI for Juvelle.

# Core Identity & Strict Grounding:
1. STRICT KNOWLEDGE BASE GROUNDING:
   - Base all answers exclusively on the provided "Relevant Juvelle Brand Knowledge" retrieved from Qdrant Cloud.
   - Do NOT fabricate or assume prices, fabrics, sizes, policies, or catalog items not present in the retrieved knowledge.
   - If an inquiry cannot be answered from the provided knowledge base, politely state that our human support team on this page will assist them.
2. AI CAPABILITIES & BOUNDARIES:
   - You are an informational customer support assistant providing product catalog details, fabrics, sizing guidance, and policies.
   - You CANNOT take orders, process bookings, create reservations, or confirm purchases directly.
   - If a customer asks to place an order, book an item, or send a screenshot for ordering, clearly state that order placement is handled manually by our human support coordinators on this page.
3. ZERO PERSONAL MEMORY HALLUCINATION (CRITICAL):
   - You DO NOT store or remember customer sizes, personal names, phone numbers, past orders, or locations across sessions.
   - If a customer asks "Do you remember me?", "Enne ormayundo?", "Who am I?", "What was my size?", or "Do you know my details?":
     - Clearly and politely explain that you are an AI assistant and do not store past personal data or specific customer profiles.
     - Never pretend to remember or guess their size (e.g., never say "Athe, S size alle nokkiyathu?", "Kollam alle location?").
     - Ask how you can assist them with Juvelle Churidar tops today.
4. CONVERSATIONAL TONE & STYLE:
   - Be concise, direct, and helpful: Keep responses to 1-2 crisp sentences.
   - Zero Emoji Spam: Do not use decorative emojis (✨, 🌸, etc.). Use clean standard punctuation.
   - Do not interrogate the customer with multiple back-to-back qualifying questions.
   - Close answers with a friendly closing (e.g., "How can I help you today?" / "Enganeya help cheyyendath?" / "Kaise madad karoon?").
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

    if target_language in ["english", "hindi_script", "malayalam_script", "tamil_script", "telugu_script"]:
        # For English and native scripts, just clean up whitespace and hyphens without stripping native characters
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
    crm_profile: Optional[Dict[str, Any]] = None,
    is_voice: bool = False
) -> str:
    """
    Executes live neural AI generation using Google Gemini model with session lifecycle guidance,
    customer CRM context, strict language mirroring, candidate cascade, and RAG grounding.
    """
    # 1. Detect language (relying on current message with is_voice flag)
    detected_lang = detect_query_language(
        message=chat_input,
        history=history,
        preferred_language=None,
        is_voice=is_voice
    )

    state = lifecycle_info.get("lifecycle_state", "first_contact") if lifecycle_info else "first_contact"
    turn_num = lifecycle_info.get("turn_count", 1) if lifecycle_info else 1
    cleaned_input = chat_input.lower().strip().rstrip("!.,? ")

    # 3. Retrieve grounded knowledge chunks from Qdrant Cloud / BM25
    retrieved_chunks = retrieve_hybrid_context(chat_input, top_k=3)
    rag_context = ""
    if retrieved_chunks:
        rag_context = "\nRelevant Juvelle Brand Knowledge (Retrieved from Knowledge Base):\n" + "\n".join([f"- {c['content']}" for c in retrieved_chunks])

    # 4. Formulate Strict Language Directive (Strictly 5 Allowed Categories)
    if detected_lang == "english":
        lang_directive = (
            "CRITICAL LANGUAGE ENFORCEMENT: The customer is speaking in ENGLISH. "
            "You MUST reply in 100% fluent, natural ENGLISH. "
            "DO NOT use ANY Malayalam, Hindi, or Manglish words."
        )
    elif detected_lang == "malayalam_script":
        lang_directive = (
            "CRITICAL LANGUAGE ENFORCEMENT: The customer is typing in MALAYALAM SCRIPT. "
            "You MUST reply in clean, grammatically correct MALAYALAM SCRIPT only."
        )
    elif detected_lang == "hindi_script":
        lang_directive = (
            "CRITICAL LANGUAGE ENFORCEMENT: The customer is typing in HINDI SCRIPT (Devanagari). "
            "You MUST reply in polite, clean Hindi in Devanagari script."
        )
    elif detected_lang == "hinglish":
        lang_directive = (
            "CRITICAL LANGUAGE ENFORCEMENT: The customer is speaking in HINGLISH (Hindi in English letters, e.g. 'kya price hai', 'cotton top dikhao'). "
            "You MUST reply in natural, polite HINGLISH using ONLY 100% English alphabet letters."
        )
    elif detected_lang == "manglish":
        lang_directive = (
            "CRITICAL LANGUAGE ENFORCEMENT: The customer is speaking in MANGLISH (Malayalam in English letters). "
            "Reply in natural, polite Manglish without hyphens or Malayalam Unicode script bleed."
        )
    else:
        lang_directive = (
            "CRITICAL LANGUAGE ENFORCEMENT: Reply in natural ENGLISH."
        )

    # 5. Formulate Session Lifecycle & Greeting Directive
    if state == "first_contact":
        if detected_lang == "english":
            lifecycle_directive = (
                "SESSION DIRECTIVE: FIRST CONTACT (Turn 1). Greet warmly in English and introduce the brand: "
                "'Hey there! Welcome to Juvelle. We specialize in daily and office wear Churidar tops. How can I help you today?'"
            )
        elif detected_lang == "hinglish":
            lifecycle_directive = (
                "SESSION DIRECTIVE: FIRST CONTACT (Turn 1). Greet warmly in Hinglish and introduce the brand: "
                "'Hey there! Welcome to Juvelle. Hum daily aur office wear Churidar tops mein specialize karte hain. Kaise help karoon?'"
            )
        elif detected_lang == "hindi_script":
            lifecycle_directive = (
                "SESSION DIRECTIVE: FIRST CONTACT (Turn 1). Greet warmly in Hindi and introduce the brand: "
                "'नमस्ते! Juvelle में आपका स्वागत है। हम डेली और ऑफिस वियर चूड़ीदार टॉप्स में स्पेशलाइज करते हैं। मैं आपकी क्या मदद कर सकता हूँ?'"
            )
        elif detected_lang == "malayalam_script":
            lifecycle_directive = (
                "SESSION DIRECTIVE: FIRST CONTACT (Turn 1). Greet warmly in Malayalam script and introduce the brand: "
                "'ഹലോ! Juvelle-ലേക്ക് സ്വാഗതം. ഞങ്ങൾ ഡെയ്‌ലി, ഓഫീസ് വെയർ ചുരിദാർ ടോപ്പുകളിൽ സ്പെഷ്യലൈസ് ചെയ്യുന്നു. എങ്ങനെയാണ് സഹായിക്കേണ്ടത്?'"
            )
        else:
            lifecycle_directive = (
                "SESSION DIRECTIVE: FIRST CONTACT (Turn 1). Greet warmly in Manglish and introduce the brand: "
                "'Hey there! Welcome to Juvelle. Nammal daily and office wear Churidar topsil specialize cheyyunnu. Enganeya help cheyyendath?'"
            )
    elif state == "returning_session":
        if detected_lang == "english":
            lifecycle_directive = (
                "SESSION DIRECTIVE: RETURNING CUSTOMER (Resuming after > 3 hrs inactivity). "
                "Start your reply in English by welcoming them back warmly: 'Welcome back to Juvelle! How can I help you today?' before answering."
            )
        elif detected_lang == "hinglish":
            lifecycle_directive = (
                "SESSION DIRECTIVE: RETURNING CUSTOMER (Resuming after > 3 hrs inactivity). "
                "Start your reply in Hinglish by welcoming them back warmly: 'Welcome back to Juvelle! Kaise help karoon?' before answering."
            )
        elif detected_lang == "hindi_script":
            lifecycle_directive = (
                "SESSION DIRECTIVE: RETURNING CUSTOMER (Resuming after > 3 hrs inactivity). "
                "Start your reply in Hindi by welcoming them back warmly: 'Juvelle में आपका स्वागत है! बताइए क्या सहायता चाहिए?' before answering."
            )
        elif detected_lang == "malayalam_script":
            lifecycle_directive = (
                "SESSION DIRECTIVE: RETURNING CUSTOMER (Resuming after > 3 hrs inactivity). "
                "Start your reply in Malayalam script by welcoming them back warmly: 'Juvelle-ലേക്ക് സ്വാഗതം! എങ്ങനെയാണ് സഹായിക്കേണ്ടത്?' before answering."
            )
        else:
            lifecycle_directive = (
                "SESSION DIRECTIVE: RETURNING CUSTOMER (Resuming after > 3 hrs inactivity). "
                "Start your reply in Manglish by welcoming them back warmly: 'Welcome back to Juvelle! Enganeya help cheyyendath?' before answering."
            )
    else:
        lifecycle_directive = (
            f"SESSION DIRECTIVE: ACTIVE ONGOING CONVERSATION (Turn {turn_num}, < 3 hrs since last message). "
            "DO NOT repeat 'Welcome to Juvelle' or deliver a brand intro! Jump straight into answering their question naturally and directly."
        )

    # 6. CRM Context Snippet (CRM COMPLETELY DETACHED - Zero profiling injection to prevent hallucinations)
    crm_context = ""

    # 7. Build conversation prompt
    dialogue_history = ""
    if history:
        for turn in history[-4:]:
            role = "Customer" if turn.get("role") == "user" else "Juvelle AI"
            content = turn.get('content', '')
            # Clean up prior unprompted "S size" hallucinations from historical context so the LLM does not repeat them
            content = re.sub(r'\b(size\s*S|S\s*size)\b', 'sizes S-XXL', content, flags=re.IGNORECASE)
            dialogue_history += f"{role}: {content}\n"

    full_prompt = (
        f"{JUVELLE_SYSTEM_PROMPT}\n\n"
        f"{lang_directive}\n\n"
        f"{lifecycle_directive}\n"
        f"{rag_context}\n\n"
        f"Conversation History:\n{dialogue_history}\n"
        f"CRITICAL REMINDER: You are Juvelle's customer support AI. You do NOT have customer order databases, personal names, tracking databases, or customer size memories. "
        f"Always answer directly in {detected_lang} without assuming specific sizes or personal order history.\n"
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

    # Dynamic fallback handling based on query intent & language
    cleaned_lower = chat_input.lower().strip()
    is_greeting_only = cleaned_lower in GREETING_WORDS or (len(cleaned_lower.split()) <= 2 and any(w in cleaned_lower for w in GREETING_WORDS))

    if state == "first_contact" and is_greeting_only:
        if detected_lang == "english":
            return "Hey there! Welcome to Juvelle. How can I help you today?"
        elif detected_lang == "hinglish":
            return "Hey there! Welcome to Juvelle. Kaise help karoon?"
        elif detected_lang == "hindi_script":
            return "नमस्ते! Juvelle में आपका स्वागत है। मैं आपकी क्या मदद कर सकता हूँ?"
        elif detected_lang == "malayalam_script":
            return "ഹലോ! Juvelle-ലേക്ക് സ്വാഗതം. എങ്ങനെയാണ് സഹായിക്കേണ്ടത്?"
        return "Hey there! Welcome to Juvelle. Enganeya help cheyyendath?"
    elif state == "returning_session" and is_greeting_only:
        if detected_lang == "english":
            return "Welcome back to Juvelle! How can I assist you today?"
        elif detected_lang == "hinglish":
            return "Welcome back to Juvelle! Kaise help karoon?"
        elif detected_lang == "hindi_script":
            return "Juvelle में आपका स्वागत है! बताइए क्या सहायता चाहिए?"
        elif detected_lang == "malayalam_script":
            return "Juvelle-ലേക്ക് സ്വാഗതം! എങ്ങനെയാണ് സഹായിക്കേണ്ടത്?"
        return "Welcome back to Juvelle! Enganeya help cheyyendath?"

    if detected_lang == "english":
        return "Our human support team on this page will assist you with details shortly. How can I help you today?"
    elif detected_lang == "hinglish":
        return "Hamari support team aapko jald hi details provide karegi. Kaise madad karoon?"
    elif detected_lang == "hindi_script":
        return "हमारी सपोर्ट टीम जल्द ही आपको विवरण प्रदान करेगी। बताइए क्या सहायता चाहिए?"
    elif detected_lang == "malayalam_script":
        return "ഞങ്ങളുടെ സപ്പോർട്ട് ടീം ഉടൻ കൂടുതൽ വിവരങ്ങൾ നൽകുന്നതാണ്. എങ്ങനെയാണ് സഹായിക്കേണ്ടത്?"
    return "Pageile support team kooduthal details tharum. Enganeya help cheyyendath?"

def generate_juvelle_response(
    chat_input: str,
    session_id: str = "default_tester",
    user_id: Optional[str] = None,
    is_voice: bool = False
) -> List[str]:
    """
    Processes customer messages with full Session Lifecycle Management, Multi-User Isolation,
    Automated CRM Profiling, Dynamic Turn-by-Turn Script Adaptation, and Real Neural AI generation.
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

    # 6. Generate concise, session-aware neural response with is_voice flag
    ai_reply = generate_live_neural_reply(chat_input, history, lifecycle_info, crm_profile, is_voice=is_voice)

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
    customer_name: Optional[str] = None,
    is_voice: bool = False
) -> str:
    """
    Convenience wrapper returning a single clean string response for voice notes and live calls.
    """
    msgs = generate_juvelle_response(
        chat_input=customer_message,
        session_id=session_id,
        user_id=customer_name or session_id,
        is_voice=is_voice
    )
    return " ".join(msgs)

