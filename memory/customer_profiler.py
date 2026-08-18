import re
import logging
from typing import Dict, Any, Optional
from memory.long_term_memory import upsert_customer_crm, get_customer_crm

logger = logging.getLogger(__name__)

# Extraction Rules & Dictionaries
SIZE_PATTERNS = [
    (r"\b(xxxl|3xl)\b", "3XL"),
    (r"\b(xxl|2xl)\b", "XXL"),
    (r"\b(xl)\b", "XL"),
    (r"\b(l|large)\b", "L"),
    (r"\b(m|medium)\b", "M"),
    (r"\b(s|small)\b", "S"),
    (r"\b(xs)\b", "XS"),
]

FABRIC_KEYWORDS = ["cotton", "rayon", "chiffon", "silk", "linen", "georgette"]

KERALA_LOCATIONS = [
    "kochi", "cochin", "ernakulam", "calicut", "kozhikode",
    "trivandrum", "thiruvananthapuram", "thrissur", "trichur",
    "kannur", "kollam", "quilon", "kottayam", "palakkad",
    "malappuram", "alappuzha", "alleppey", "wayanad", "kasaragod",
    "idukki", "pathanamthitta"
]

ORDER_INTENT_KEYWORDS = [
    "order", "book", "gpay", "google pay", "phonepe", "upi",
    "pay", "buy", "purchase", "address tharam", "send address",
    "account details", "bank transfer", "confirm"
]

BROWSING_INTENT_KEYWORDS = [
    "model", "models", "photos", "pics", "color", "colours",
    "price", "rate", "cost", "churidar", "collection", "stock",
    "available", "catalogue", "catalog"
]

SUPPORT_INTENT_KEYWORDS = [
    "tracking", "courier", "status", "dispatch", "delivery eppo",
    "reach", "delay", "not received", "item vannilla", "complaint"
]

MANGLISH_INDICATORS = {
    "undu", "undo", "aanu", "aano", "alla", "allathe", "enthaanu", "enthanu", "enthokke", "enthokkeya",
    "kanikku", "kaanikku", "kaanikkatte", "kanikkatte", "ethraya", "ethra", "nokkunnath", "nokkunath",
    "nokkatte", "nokkoo", "cheyyatte", "cheyyam", "cheyyuka", "cheythal", "parayuu", "parayu", "athe",
    "illa", "alle", "kootuthal", "keralathil", "evide", "ivide", "engane", "enganeya", "vellom", "onnum",
    "matte", "ithu", "athu", "njan", "nammal", "nammude", "ningal", "valare", "ippol", "eppo", "vannu",
    "vannilla", "kittumo", "kittum", "venam", "venda", "sahayam", "tharam", "ayakkanam", "ayakkamo",
    "nalla", "ishtam", "undallo", "undath", "cheytholu", "nokkikoloo", "evideya", "aayitt"
}

def extract_language_signal(message: str) -> Optional[str]:
    """Extracts language signal from customer message."""
    if not message:
        return None
    # 1. Malayalam Script
    if len(re.findall(r'[\u0D00-\u0D7F]', message)) >= 2:
        return "malayalam_script"
    
    # 2. Manglish Keywords
    words = set(re.findall(r'[a-zA-Z]+', message.lower()))
    if words.intersection(MANGLISH_INDICATORS):
        return "manglish"
    
    # 3. Explicit English structure
    english_cues = {"only", "need", "needed", "nephew", "t-shirt", "shirt", "what", "where", "when", "why", "how", "have", "deliver", "shipping", "price", "show", "collection"}
    if words.intersection(english_cues) or (len(words) >= 2 and not words.intersection(MANGLISH_INDICATORS)):
        return "english"
    return None

def analyze_and_profile_customer(user_id: str, message: str) -> Dict[str, Any]:
    """
    Extracts key demographic, preference, intent, and language signals from a customer's message,
    and updates the long-term CRM dossier.
    """
    msg_clean = message.lower()

    # 1. Size Extraction
    detected_size: Optional[str] = None
    for pattern, size_val in SIZE_PATTERNS:
        if re.search(pattern, msg_clean, re.IGNORECASE):
            detected_size = size_val
            break

    # 2. Fabric Extraction
    detected_fabric: Optional[str] = None
    for fabric in FABRIC_KEYWORDS:
        if fabric in msg_clean:
            detected_fabric = fabric.capitalize()
            break

    # 3. Location Extraction
    detected_location: Optional[str] = None
    for loc in KERALA_LOCATIONS:
        if loc in msg_clean:
            detected_location = loc.capitalize()
            break

    # 4. Language Signal Extraction
    detected_lang = extract_language_signal(message)

    # 5. Lifecycle Stage Detection
    detected_stage: Optional[str] = None
    tags = []

    if any(kw in msg_clean for kw in ORDER_INTENT_KEYWORDS):
        detected_stage = "Ready to Order"
        tags.append("High Intent")
    elif any(kw in msg_clean for kw in SUPPORT_INTENT_KEYWORDS):
        detected_stage = "Support"
        tags.append("Post-Purchase Support")
    elif any(kw in msg_clean for kw in BROWSING_INTENT_KEYWORDS):
        detected_stage = "Browsing"
        tags.append("Shopper")

    if detected_size:
        tags.append(f"Size:{detected_size}")
    if detected_fabric:
        tags.append(f"Fabric:{detected_fabric}")
    if detected_location:
        tags.append(f"Location:{detected_location}")
    if detected_lang:
        tags.append(f"Lang:{detected_lang.capitalize()}")

    # 6. Persist to CRM SQLite
    try:
        updated_crm = upsert_customer_crm(
            user_id=user_id,
            preferred_size=detected_size,
            preferred_fabric=detected_fabric,
            preferred_language=detected_lang,
            location=detected_location,
            stage=detected_stage,
            tags=tags if tags else None
        )
        return updated_crm
    except Exception as e:
        logger.error(f"Failed to update customer CRM profile: {e}")
        return {"user_id": user_id, "error": str(e)}

