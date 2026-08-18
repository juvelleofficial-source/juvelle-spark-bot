import unittest
import time
from fastapi.testclient import TestClient
from api.main import app
from mcp_server.tools_registry import execute_mcp_tool
from mcp_server.message_queue import get_message_reply, get_pending_messages
from ingestion.ingestion_job import run_ingestion_pipeline
from core.juvelle_agent import sanitize_manglish_response, generate_juvelle_response
from memory.short_term_memory import memory_manager

class TestGeminiSparkPureMCP(unittest.TestCase):
    """
    Unit & integration tests verifying Pure Gemini Spark MCP Architecture and Juvelle Conversational Flow.
    """

    @classmethod
    def setUpClass(cls):
        run_ingestion_pipeline()

    def setUp(self):
        self.client = TestClient(app)

    def test_01_mcp_sse_head_probe(self):
        """Verify Google Gemini Spark validation probe HEAD /mcp/sse returns 200 OK"""
        resp = self.client.head("/mcp/sse")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.headers.get("content-type", ""))

    def test_02_mcp_jsonrpc_initialize(self):
        """Verify MCP initialize handshake returns server info and protocol version"""
        payload = {
            "jsonrpc": "2.0",
            "id": "init_test",
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"}
        }
        resp = self.client.post("/mcp/messages", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["result"]["protocolVersion"], "2024-11-05")
        self.assertIn("Gemini", data["result"]["serverInfo"]["name"])

    def test_03_mcp_tools_list(self):
        """Verify tools/list exposes all 4 tools required for autonomous Spark agent"""
        payload = {
            "jsonrpc": "2.0",
            "id": "list_test",
            "method": "tools/list",
            "params": {}
        }
        resp = self.client.post("/mcp/messages", json=payload)
        self.assertEqual(resp.status_code, 200)
        tools = resp.json()["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("get_pending_facebook_messages", tool_names)
        self.assertIn("search_knowledge_base", tool_names)
        self.assertIn("send_facebook_reply", tool_names)
        self.assertIn("save_customer_note", tool_names)

    def test_04_mcp_tool_execution_search_knowledge_base(self):
        """Verify search_knowledge_base retrieves accurate offline facts with zero API keys"""
        res = execute_mcp_tool("search_knowledge_base", {"query": "pricing and fabrics", "top_k": 2})
        self.assertNotIn("error", res)
        self.assertGreater(res["results_count"], 0)

    def test_05_end_to_end_spark_inbox_flow(self):
        """Verify message enqueueing and Spark send_facebook_reply resolution"""
        from mcp_server.message_queue import enqueue_facebook_message
        # 1. Enqueue inquiry into MCP Inbox
        msg_id = enqueue_facebook_message(
            sender_id="spark_flow_test",
            message_text="Do you deliver to Bangalore?",
            sender_name="Tester Spark",
            platform="instagram"
        )
        self.assertTrue(msg_id.startswith("fb_"))

        # 2. Spark fetches pending messages
        pending = execute_mcp_tool("get_pending_facebook_messages", {"limit": 5})
        messages = pending["messages"]
        self.assertTrue(any(m["sender_id"] == "spark_flow_test" for m in messages))
        target_msg = next(m for m in messages if m["sender_id"] == "spark_flow_test")

        # 3. Spark sends reply
        reply_res = execute_mcp_tool("send_facebook_reply", {
            "message_id": target_msg["message_id"],
            "recipient_id": target_msg["sender_id"],
            "reply_text": "Juvelle delivers exclusively within Kerala via Delhivery."
        })
        self.assertEqual(reply_res["status"], "delivered")

        # 4. Verify reply was persisted in queue
        saved_reply = get_message_reply(target_msg["message_id"])
        self.assertIn("Kerala", saved_reply)


    def test_06_emoji_sanitizer_removes_spam(self):
        """Verify sanitize_manglish_response removes flower and sparkle spam"""
        raw = "Hey there! Welcome to Juvelle 🌸 We specialize in tops ✨🌸"
        cleaned = sanitize_manglish_response(raw)
        self.assertNotIn("✨", cleaned)
        self.assertNotIn("🌸", cleaned)

    def test_07_mid_conversation_hi_does_not_reset_greeting(self):
        """Verify saying 'hi' in an active ongoing session does not re-introduce the brand"""
        sess_id = f"test_user_active_{int(time.time())}"
        
        # Turn 1: Initial question
        resp1 = self.client.post(
            "/webhook/instagram-test",
            json={"chatInput": "Do you have tops for office?", "sessionId": sess_id}
        )
        self.assertEqual(resp1.status_code, 200)
        
        # Turn 2: User says "hi" mid-conversation
        resp2 = self.client.post(
            "/webhook/instagram-test",
            json={"chatInput": "hi", "sessionId": sess_id}
        )
        self.assertEqual(resp2.status_code, 200)
        reply2 = resp2.json()["output"][0]
        
        # It must NOT return the full first-time onboarding introduction
        self.assertNotIn("Welcome to Juvelle", reply2)
        self.assertIn("Hey", reply2)

    def test_08_no_photo_send_offer(self):
        """Verify the bot does NOT offer to send photos or ask 'photo send cheyyatte?'"""
        sess_id = f"test_user_photo_{int(time.time())}"
        
        resp = self.client.post(
            "/webhook/instagram-test",
            json={"chatInput": "kanikku", "sessionId": sess_id}
        )
        self.assertEqual(resp.status_code, 200)
        reply = " ".join(resp.json()["output"])
        self.assertNotIn("photo send cheyyatte", reply.lower())
        self.assertNotIn("✨", reply)
        self.assertNotIn("🌸", reply)

if __name__ == "__main__":
    unittest.main()
