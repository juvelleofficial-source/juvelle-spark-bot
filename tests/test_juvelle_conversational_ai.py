import unittest
from fastapi.testclient import TestClient
from api.main import app
from mcp_server.tools_registry import execute_mcp_tool
from mcp_server.message_queue import get_message_reply, get_pending_messages
from ingestion.ingestion_job import run_ingestion_pipeline

class TestGeminiSparkPureMCP(unittest.TestCase):
    """
    Unit & integration tests verifying Pure Gemini Spark MCP Architecture (Zero API Keys).
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
        # 1. Enqueue inquiry via tester webhook
        post_resp = self.client.post(
            "/webhook/instagram-test",
            json={"chatInput": "Do you deliver to Bangalore?", "sessionId": "spark_flow_test"}
        )
        self.assertEqual(post_resp.status_code, 200)

        # 2. Spark fetches pending messages
        pending = execute_mcp_tool("get_pending_facebook_messages", {"limit": 5})
        messages = pending["messages"]
        self.assertTrue(any(m["sender_id"] == "spark_flow_test" for m in messages))
        target_msg = next(m for m in messages if m["sender_id"] == "spark_flow_test")

        # 3. Spark sends reply
        reply_res = execute_mcp_tool("send_facebook_reply", {
            "message_id": target_msg["message_id"],
            "recipient_id": target_msg["sender_id"],
            "reply_text": "Juvelle delivers exclusively within Kerala via Delhivery! ✨"
        })
        self.assertEqual(reply_res["status"], "delivered")

        # 4. Verify reply was persisted in queue
        saved_reply = get_message_reply(target_msg["message_id"])
        self.assertIn("Kerala", saved_reply)

if __name__ == "__main__":
    unittest.main()
