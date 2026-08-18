import os
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

META_PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN", None)
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "gemini_spark_secret_verify_token")

def send_meta_graph_reply(recipient_id: str, message_text: str) -> Dict[str, Any]:
    """
    Sends a message reply to a customer via Meta Graph API (Messenger/WhatsApp/Instagram).
    Falls back gracefully to simulated logging if no Meta access token is configured.
    """
    if not META_PAGE_ACCESS_TOKEN:
        logger.info(f"[SIMULATED META DISPATCH] Recipient: {recipient_id} | Reply: '{message_text}'")
        return {
            "status": "success",
            "mode": "simulated",
            "recipient_id": recipient_id,
            "message": "Message dispatched successfully (Simulated mode: set META_PAGE_ACCESS_TOKEN for live delivery)."
        }

    url = "https://graph.facebook.com/v19.0/me/messages"
    headers = {
        "Authorization": f"Bearer {META_PAGE_ACCESS_TOKEN}",
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
            logger.info(f"Successfully sent Meta message: {res_data}")
            return {"status": "success", "mode": "live", "meta_response": res_data}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error(f"Meta Graph API error ({e.code}): {error_body}")
        return {"status": "error", "code": e.code, "error": error_body}
    except Exception as e:
        logger.error(f"Failed to send Meta message: {e}")
        return {"status": "error", "error": str(e)}
