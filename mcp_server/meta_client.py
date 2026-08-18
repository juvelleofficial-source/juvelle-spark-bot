import os
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

META_PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN", None)
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "gemini_spark_secret_verify_token")

def _get_token(custom_token: Optional[str] = None) -> Optional[str]:
    if custom_token:
        return custom_token
    token = os.getenv("META_PAGE_ACCESS_TOKEN", None)
    if token:
        return token
    # Try reading from root .env or mcp_server/.env
    for candidate in [
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        os.path.join(os.path.dirname(__file__), ".env"),
        ".env"
    ]:
        if os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("META_PAGE_ACCESS_TOKEN="):
                            return line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass
    return None

def send_meta_graph_reply(recipient_id: str, message_text: str, custom_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Sends a message reply to a customer via Meta Graph API (Messenger/WhatsApp/Instagram).
    Falls back gracefully to simulated logging if no Meta access token is configured.
    """
    token = _get_token(custom_token)
    
    if not token:
        logger.info(f"[SIMULATED META DISPATCH] Recipient: {recipient_id} | Reply: '{message_text}'")
        return {
            "status": "success",
            "mode": "simulated",
            "recipient_id": recipient_id,
            "message": "Message dispatched successfully (Simulated mode: set META_PAGE_ACCESS_TOKEN for live delivery)."
        }

    url = "https://graph.facebook.com/v21.0/me/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": "RESPONSE",
        "message": {"text": message_text}
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            logger.info(f"Successfully sent Meta message to {recipient_id}: {res_data}")
            return {"status": "success", "mode": "live", "meta_response": res_data}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error(f"Meta Graph API error ({e.code}): {error_body}")
        return {"status": "error", "code": e.code, "error": error_body}
    except Exception as e:
        logger.error(f"Failed to send Meta message: {e}")
        return {"status": "error", "error": str(e)}

