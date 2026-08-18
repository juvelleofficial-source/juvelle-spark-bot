#!/usr/bin/env python3
"""
External Keep-Alive and Uptime Monitor for Juvelle Bot on Render.
Sends true external HTTP GET/HEAD requests to prevent Render free-tier idle spin-down.
"""

import sys
import time
import datetime
import urllib.request
import urllib.error
import json
import io

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

DEFAULT_TARGETS = [
    "https://juvelle-spark-bot.onrender.com/api/health",
    "https://juvelle-spark-bot.onrender.com/health",
    "https://juvelle-spark-bot.onrender.com/ping",
    "https://juvelle-spark-bot.onrender.com/mcp/sse"
]

def ping_url(url: str, timeout: int = 15) -> dict:
    """Sends an external HTTP request and returns status and latency."""
    start = time.time()
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Juvelle-External-KeepAlive/2.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency_ms = round((time.time() - start) * 1000, 2)
            return {
                "url": url,
                "status_code": resp.getcode(),
                "success": 200 <= resp.getcode() < 400,
                "latency_ms": latency_ms,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
    except urllib.error.HTTPError as e:
        latency_ms = round((time.time() - start) * 1000, 2)
        return {
            "url": url,
            "status_code": e.code,
            "success": e.code in [200, 301, 302, 307, 308],
            "latency_ms": latency_ms,
            "error": str(e),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
    except Exception as e:
        latency_ms = round((time.time() - start) * 1000, 2)
        return {
            "url": url,
            "status_code": 0,
            "success": False,
            "latency_ms": latency_ms,
            "error": str(e),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

def run_external_keepalive_check(targets=None):
    """Performs a comprehensive ping across all target endpoints."""
    if not targets:
        targets = DEFAULT_TARGETS
    
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting External Render Keep-Alive Ping...")
    results = []
    any_success = False

    for target in targets:
        res = ping_url(target)
        results.append(res)
        status_icon = "[OK]" if res["success"] else "[WARN]"
        print(f"  {status_icon} {res['url']} -> Status: {res['status_code']} ({res['latency_ms']}ms)")
        if res["success"]:
            any_success = True

    if any_success:
        print("  -> Render service successfully received external traffic and idle timer is reset.")
    else:
        print("  -> Warning: All target endpoints failed to respond.")
    
    return results

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--loop":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        print(f"Running continuous keep-alive loop every {interval} seconds...")
        while True:
            run_external_keepalive_check()
            time.sleep(interval)
    else:
        run_external_keepalive_check()
