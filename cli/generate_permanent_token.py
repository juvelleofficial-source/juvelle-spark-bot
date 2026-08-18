import urllib.request
import urllib.parse
import json
import os
import sys

def exchange_short_lived_token_for_permanent(
    short_lived_user_token: str,
    app_id: str = "25549623661375252",
    app_secret: str = "c82705e468305c48684d0df09b2e2d93",
    page_id: str = "932916046574692"
) -> dict:
    """
    Exchanges a short-lived user token into a 60-day long-lived user token,
    and then extracts a NEVER-EXPIRING Permanent Page Access Token.
    """
    print("=== Step 1: Exchanging Short-Lived Token for Long-Lived Token ===")
    exchange_params = urllib.parse.urlencode({
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_lived_user_token.strip()
    })
    
    exchange_url = f"https://graph.facebook.com/v21.0/oauth/access_token?{exchange_params}"
    
    try:
        with urllib.request.urlopen(exchange_url) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            long_lived_user_token = data.get("access_token")
            expires_in = data.get("expires_in", 5184000) # ~60 days
            print(f"[SUCCESS] Acquired 60-day Long-Lived User Token (expires in {expires_in//86400} days).")
    except Exception as e:
        return {"status": "error", "step": "exchange", "message": str(e)}
        
    print("\n=== Step 2: Extracting Permanent Never-Expiring Page Access Token ===")
    page_url = f"https://graph.facebook.com/v21.0/{page_id}?fields=access_token,name&access_token={long_lived_user_token}"
    
    try:
        with urllib.request.urlopen(page_url) as resp:
            page_data = json.loads(resp.read().decode("utf-8"))
            permanent_page_token = page_data.get("access_token")
            page_name = page_data.get("name")
            print(f"[SUCCESS] Extracted Permanent Page Token for Page '{page_name}' ({page_id})!")
    except Exception as e:
        return {"status": "error", "step": "page_token_extraction", "message": str(e)}
        
    print("\n=== Step 3: Verifying Token Expiration via Debug Token API ===")
    debug_url = f"https://graph.facebook.com/v21.0/debug_token?input_token={permanent_page_token}&access_token={permanent_page_token}"
    
    try:
        with urllib.request.urlopen(debug_url) as resp:
            debug_data = json.loads(resp.read().decode("utf-8")).get("data", {})
            expires_at = debug_data.get("expires_at", 0)
            is_valid = debug_data.get("is_valid", False)
            scopes = debug_data.get("scopes", [])
            
            exp_str = "NEVER EXPIRES (Permanent)" if expires_at == 0 else f"Expires at timestamp {expires_at}"
            print(f"Token Validity: {is_valid}")
            print(f"Expiration: {exp_str}")
            print(f"Active Scopes: {', '.join(scopes)}")
    except Exception as e:
        print(f"Debug Token notice: {e}")
        
    return {
        "status": "success",
        "page_id": page_id,
        "permanent_page_token": permanent_page_token,
        "expires_at": "never"
    }

if __name__ == "__main__":
    if len(sys.argv) > 1:
        tok = sys.argv[1]
        res = exchange_short_lived_token_for_permanent(tok)
        print("\nFINAL RESULT:", res)
    else:
        print("Usage: python cli/generate_permanent_token.py <SHORT_LIVED_TOKEN>")
