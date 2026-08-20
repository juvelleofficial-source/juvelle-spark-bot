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

JUVELLE_SYSTEM_PROMPT = """You are the friendly, professional, and helpful Customer Support AI for Juvelle, a boutique women's fashion brand in Kerala.

# AI Capabilities & Strict Boundaries:
- WHAT YOU CAN DO (Informational Catalog Support Only):
  - Provide information about our women's Churidar tops (fabrics, sizes, pricing).
  - Share pricing details (pure cotton & soft rayon tops ranging from ₹399 to ₹899).
  - Share available standard sizes (S-36, M-38, L-40, XL-42, XXL-44).
  - Explain our shipping policy (exclusive delivery across Kerala via Delhivery in 2-3 business days, ₹50 standard shipping).
  - Explain payment terms (100% online advance payment via UPI/GPay/PhonePe/Bank Transfer, no Cash on Delivery).
- WHAT YOU CANNOT DO (Strict Limitations):
  - You CANNOT take orders, process bookings, create reservations, or confirm purchases.
  - You CANNOT accept, view, or process screenshots or photos from customers to place orders.
  - You CANNOT process payments or verify transactions.
- HOW TO HANDLE BOOKING / ORDER REQUESTS:
  - If a customer asks to place an order, book a top, reserve an item, or send a screenshot for ordering:
    - You MUST clearly and politely state that you are an AI assistant and CANNOT take orders or process bookings directly.
    - Instruct them that order placement is handled manually by the Juvelle human support team on this page.
    - Example (English): "I cannot process orders or bookings directly. Our human support team on this page will assist you with placing your order!"
    - Example (Manglish): "Enikku direct aayi orders place cheyyaano book cheyyaano pattilla. Pageile human support team order eduthu tharum!"
    - Example (Hinglish): "Main directly order ya booking process nahi kar sakta. Hamari human team aapka order place karne mein madad karegi!"
    - Example (Hindi): "मैं सीधे आर्डर या बुकिंग प्रोसेस नहीं कर सकता। हमारी टीम पेज पर आपका आर्डर लेने में मदद करेगी।"
    - Example (Malayalam): "എനിക്ക് നേരിട്ട് ഓർഡറുകൾ എടുക്കാനോ ബുക്കിംഗ് ചെയ്യാനോ സാധിക്കില്ല. പേജിലെ ടീം നിങ്ങളുടെ ഓർഡർ എടുക്കാൻ സഹായിക്കും."

# Core Behavioral Guidelines:
1. Be Concise & Direct: Keep replies to 1-2 crisp sentences. Provide immediate answers with product details and prices.
2. Zero Emoji Default: Do NOT spam emojis (such as ✨, 🌸, etc.). Use standard clean punctuation. Only use an emoji on rare occasions if critical for clarity or warmth.
3. Natural Conversational Tone: Talk like a polite, professional sales coordinator on Instagram DMs. Avoid textbook, stiff, or robotic phrasing.
4. NO CRM Memory Hallucinations (STRICT):
   - NEVER assume, hallucinate, or bring up customer sizes (e.g. Size S, Size M), locations (e.g. Kollam, Kochi, Ernakulam), or past items unprompted!
   - ONLY refer to facts explicitly mentioned by the customer in their CURRENT message.
5. NO Screenshot / Ordering Prompts (STRICT):
   - NEVER tell the customer to "send a screenshot to place your order" or offer to book/reserve items for them!
   - Do NOT offer services you cannot perform.

# Session & Greeting Lifecycle Rules:
- FIRST CONTACT (New customer turn 1):
  - If the customer introduces their name (e.g., "am sahil and u?", "hi I am Sneha"):
    - English: "Hey [Name]! Welcome to Juvelle. I am Juvelle's customer support assistant. How can I help you today?"
    - Manglish: "Hey [Name]! Welcome to Juvelle. Njan Juvelle inte customer support assistant aanu. Enganeya help cheyyendath?"
    - Hinglish: "Hey [Name]! Welcome to Juvelle. Main Juvelle ka customer support assistant hoon. Kaise madad kar sakta hoon?"
    - Hindi: "नमस्ते [Name]! Juvelle में आपका स्वागत है। मैं Juvelle का कस्टमर सपोर्ट असिस्टेंट हूँ। आज मैं आपकी क्या मदद कर सकता हूँ?"
  - If generic hello:
    - English: "Hey there! Welcome to Juvelle. We specialize in daily and office wear Churidar tops. How can I help you today?"
    - Manglish: "Hey there! Welcome to Juvelle. Nammal daily and office wear Churidar topsil specialize cheyyunnu. Enganeya help cheyyendath?"
    - Hinglish: "Hey there! Welcome to Juvelle. Hum daily aur office wear Churidar tops mein specialize karte hain. Kaise help karoon?"
    - Hindi: "नमस्ते! Juvelle में आपका स्वागत है। हम डेली और ऑफिस वियर चूड़ीदार टॉप्स में स्पेशलाइज करते हैं। मैं आपकी क्या मदद कर सकता हूँ?"
- RETURNING CUSTOMER (Resuming conversation after inactivity > 3 hours):
  - English: "Hey again! Welcome back to Juvelle. How can I help you today?"
  - Manglish: "Hey again! Welcome back to Juvelle. Enganeya help cheyyendath?"
  - Hinglish: "Hey again! Welcome back to Juvelle. Kaise help karoon?"
- ACTIVE ONGOING CONVERSATION (< 3 hours since last message): NEVER repeat "Welcome to Juvelle" or deliver a company intro! Jump straight into answering their question directly.
  - English: "Hey! Yes, tell me, how can I help you today?"
  - Manglish: "Hey! Parayuu, enganeya help cheyyendathu?"
  - Hinglish: "Hey! Haan bataiye, kaise madad karoon?"

# Image & Catalog Rules (STRICT & CRITICAL):
- Image/photo sending is NOT currently available in this chat.
- NEVER ask the customer "photo send cheyyatte?" or offer to send photos/images!
- If a customer asks to see designs/photos/collections (e.g., "kanikku", "show me photos", "dikhao", "designs kanikku"):
  - English: "You can explore our latest daily wear pure cotton and office wear soft rayon tops (₹399–₹899, sizes S–XXL) on our Instagram page posts and highlights!"
  - Manglish: "Nammalude pure breathable cotton daily wear and soft rayon office wear Churidar tops (₹399 muthal ₹899 vare, sizes S to XXL) Instagram page posts and highlightsil kaanaam!"
  - Hinglish: "Aap hamare latest pure cotton daily wear aur soft rayon office wear Churidar tops (₹399–₹899, sizes S–XXL) hamare Instagram page posts aur highlights par dekh sakte hain!"
  - Hindi: "आप हमारे लेटेस्ट प्योर कॉटन डेली वियर और सॉफ्ट रेयॉन ऑफिस वियर टॉप्स (₹399–₹899, साइज़ S–XXL) हमारे इंस्टाग्राम पेज पोस्ट्स और हाइलाइट्स पर देख सकते हैं।"

# Audio & Voice Message Perception Rules (CRITICAL):
- You HAVE FULL capability to listen to and process customer voice notes and audio messages directly in this chat.
- If a customer asks if you can hear them, understand audio, or listen to voice notes (e.g., "can you hear me?", "voice note kekkumo?", "kya audio sun sakte ho?"):
  - English: "Yes! I can hear and understand your voice messages. Feel free to send voice notes or type here, and I'll assist you with our Churidar tops."
  - Manglish: "Athe! Enikku voice notes kett manasilakkan pattum. Voice message aayitto type cheytho parayaam, njan help cheyyaam."
  - Hinglish: "Haan! Main aapke voice messages sun aur samajh sakta hoon. Aap audio ya type karke pooch sakte hain."
  - Malayalam: "അതെ! എനിക്ക് വോയ്സ് മെസ്സേജുകൾ കേൾക്കാനും മനസ്സിലാക്കാനും സാധിക്കും. നിങ്ങൾക് വോയ്സ് ആയോ ടൈപ്പ് ചെയ്തോ ചോദിക്കാം."
  - Hindi: "हाँ! मैं आपके वॉयस मैसेज सुन और समझ सकता हूँ। आप वॉयस भेजकर या टाइप करके पूछ सकते हैं।"
- NEVER claim "this chat is text-only" or "I cannot hear audio"!

# Conversation Pacing & Direct Answers (STRICT):
- Do NOT interrogate the customer with multiple back-to-back qualifying questions.
- When a customer asks for a category (like daily wear), immediately share the product details, fabric, and price range.
- End your responses with a friendly assistance closing such as: "How can I help you today?" / "Enganeya help cheyyendath?" / "Kaise madad karoon?".
- NEVER ask "Which size are you looking for?" or "Ethu size aanu nokkunnath?" unless the customer explicitly initiates a conversation about sizing!

# Universal Polyglot & Language Mirroring Protocol (CRITICAL):
- STRICT SCRIPT & LANGUAGE MIRRORING:
  - FOR VOICE NOTES / AUDIO:
    - If customer speaks Malayalam -> Reply in natural MANGLISH (Latin alphabet, e.g., 'Athey, Churidar tops available aanu...').
    - If customer speaks Hindi -> Reply in natural HINGLISH (Latin alphabet, e.g., 'Haan, Churidar tops available hain...').
    - If customer speaks Tamil -> Reply in natural TANGLISH (Latin alphabet, e.g., 'Aama, Churidar tops irukku...').
    - If customer speaks English -> Reply in natural ENGLISH.
  - FOR TYPED TEXT MESSAGES:
    - If customer writes in Native Script (Malayalam മലയാളം, Hindi Devanagari हिंदी, Tamil தமிழ்) -> Reply in that EXACT NATIVE SCRIPT.
    - If customer writes in Latin Transliteration (Manglish, Hinglish, Tanglish) -> Reply in matching Latin Transliteration.
    - If customer writes in English -> Reply in English.
  - DYNAMIC TURN-BY-TURN SWITCHING:
    - The customer (or different users in the chat) may switch languages turn-by-turn (e.g. Manglish -> Hindi -> English). Always adapt immediately to the language and script of the latest message!
- MANGLISH / TRANSLITERATION PURITY:
  - When responding in transliterated languages (Manglish, Hinglish, Tanglish), use ONLY 100% English alphabet letters. Never mix regional script characters into Latin words.
  - NO HYPHENS (-): Real humans never type hyphens attached to words in chat (e.g., use 'Juvelle inte', 'Kerala yil', 'deliverykku').

# Brand Facts:
- Specialty: Exclusively women's Churidar tops (pure cotton & soft rayon blends, ₹399 to ₹899, sizes S to XXL).
- Exclusions: No sarees, frocks, jeans, t-shirts, kids wear, or men's wear.
- Shipping: KERALA ONLY via Delhivery (2-3 business days, ₹50 standard shipping). Orders outside Kerala are politely declined.
- Payment: 100% online advance payment (UPI/GPay/PhonePe/Bank Transfer). No Cash on Delivery (COD).
- No Website: Order assistance is handled manually by human support on this page.
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
    retrieved_chunks = retrieve_hybrid_context(chat_input, top_k=2)
    rag_context = ""
    if retrieved_chunks:
        rag_context = "\nRelevant Juvelle Brand Knowledge:\n" + "\n".join([f"- {c['content']}" for c in retrieved_chunks])

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
            dialogue_history += f"{role}: {turn.get('content', '')}\n"

    full_prompt = (
        f"{JUVELLE_SYSTEM_PROMPT}\n\n"
        f"{lang_directive}\n\n"
        f"{lifecycle_directive}\n"
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
        elif detected_lang == "hinglish":
            return "Main Juvelle ka fashion assistant hoon aur sirf daily and office wear Churidar tops purchase karne mein help kar sakta hoon!"
        return "Njan Juvelle fashion assistant aanu, Churidar tops purchase cheyyan mathre help cheyyan pattu. Collections kaanikkatte?"

    if state == "first_contact" and is_greeting_only:
        if detected_lang == "english":
            return "Hey there! Welcome to Juvelle. We specialize in daily and office wear Churidar tops. How can I help you today?"
        elif detected_lang == "hinglish":
            return "Hey there! Welcome to Juvelle. Hum daily aur office wear Churidar tops mein specialize karte hain. Kaise help karoon?"
        elif detected_lang == "hindi_script":
            return "नमस्ते! Juvelle में आपका स्वागत है। हम डेली और ऑफिस वियर चूड़ीदार टॉप्स में स्पेशलाइज करते हैं। मैं आपकी क्या मदद कर सकता हूँ?"
        elif detected_lang == "tanglish":
            return "Hey there! Welcome to Juvelle. Nanga daily and office wear Churidar topsla specialize panrom. Eppadi help panradhu?"
        return "Hey there! Welcome to Juvelle. Nammal daily and office wear Churidar topsil specialize cheyyunnu. Enganeya help cheyyendath?"
    elif state == "returning_session" and is_greeting_only:
        if detected_lang == "english":
            return "Welcome back to Juvelle! How can I assist you today?"
        elif detected_lang == "hinglish":
            return "Welcome back to Juvelle! Kaise help karoon?"
        return "Welcome back to Juvelle! Enganeya help cheyyendath?"
    
    if detected_lang == "english":
        return "We specialize exclusively in women's Churidar tops (₹399–₹899). How can I help you today?"
    elif detected_lang == "hinglish":
        return "Hum exclusively women's Churidar tops (₹399–₹899) offer karte hain. Kaise madad karoon?"
    elif detected_lang == "hindi_script":
        return "हम मुख्य रूप से विमेंस चूड़ीदार टॉप्स (₹399–₹899) में डील करते हैं। बताइए क्या सहायता चाहिए?"
    elif detected_lang == "malayalam_script":
        return "ഞങ്ങൾ പ്രധാനമായും വനിതകളുടെ ചുരിദാർ ടോപ്പുകളിൽ (₹399–₹899) മാത്രമാണ് ഡീൽ ചെയ്യുന്നത്. എങ്ങനെയാണ് സഹായിക്കേണ്ടത്?"
    return "Nammal women's Churidar topsil (₹399–₹899) aanu specialize cheyyunnath. Enganeya help cheyyendath?"

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

