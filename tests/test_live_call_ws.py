import os
import sys
import json
import unittest
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from api.main import app
from core.live_call_manager import live_call_manager

class TestLiveCallWebSocket(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_live_call_websocket_lifecycle(self):
        """Verify WebSocket handshake, greeting, ping-pong, and graceful hangup."""
        session_id = "test_live_caller_1"
        with self.client.websocket_connect(f"/api/live-call/{session_id}") as websocket:
            # 1. Receive initial connected handshake
            data1 = websocket.receive_json()
            self.assertEqual(data1["type"], "connected")
            self.assertEqual(data1["session_id"], session_id)

            # 2. Receive initial bot speech greeting
            data2 = websocket.receive_json()
            self.assertEqual(data2["type"], "bot_speech")
            self.assertIn("Juvelle", data2["text"])

            # 3. Send ping frame
            websocket.send_text(json.dumps({"action": "ping"}))
            pong_resp = websocket.receive_json()
            self.assertEqual(pong_resp["type"], "pong")

            # 4. Send hangup frame
            websocket.send_text(json.dumps({"action": "hangup"}))

    def test_multi_session_concurrency(self):
        """Verify multiple simultaneous live calls with isolated session IDs."""
        s1 = "caller_session_A"
        s2 = "caller_session_B"
        
        with self.client.websocket_connect(f"/api/live-call/{s1}") as ws1:
            with self.client.websocket_connect(f"/api/live-call/{s2}") as ws2:
                # Both callers connected simultaneously
                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()
                
                self.assertEqual(msg1["session_id"], s1)
                self.assertEqual(msg2["session_id"], s2)
                
                ws1.send_text(json.dumps({"action": "hangup"}))
                ws2.send_text(json.dumps({"action": "hangup"}))

if __name__ == "__main__":
    unittest.main()
