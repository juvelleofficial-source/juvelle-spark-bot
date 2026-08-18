import unittest
import json
from fastapi.testclient import TestClient
from api.main import app
from mcp_server.meta_client import META_VERIFY_TOKEN
from mcp_server.tools_registry import MCP_TOOLS_MANIFEST, execute_mcp_tool
from mcp_server.message_queue import enqueue_facebook_message, get_pending_messages
from ingestion.ingestion_job import run_ingestion_pipeline

class TestGeminiSparkMCPServer(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        # Ensure knowledge base vectors are indexed for RAG tool tests
        run_ingestion_pipeline()

    def test_mcp_initialize(self):
        """Verify Gemini Spark MCP initialization handshake."""
        payload = {
            "jsonrpc": "2.0",
            "id": "init_1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "Gemini-Spark-Web-Client", "version": "1.0.0"}
            }
        }
        res = self.client.post("/mcp/messages", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["result"]["protocolVersion"], "2024-11-05")
        self.assertIn("tools", data["result"]["capabilities"])

    def test_mcp_tools_list(self):
        """Verify Gemini Spark MCP tool discovery listing."""
        payload = {
            "jsonrpc": "2.0",
            "id": "list_1",
            "method": "tools/list",
            "params": {}
        }
        res = self.client.post("/mcp/messages", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        tools = data["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("get_pending_facebook_messages", tool_names)
        self.assertIn("search_knowledge_base", tool_names)
        self.assertIn("send_facebook_reply", tool_names)
        self.assertIn("save_customer_note", tool_names)

    def test_facebook_webhook_handshake(self):
        """Verify Meta Webhook verification handshake."""
        res = self.client.get(f"/webhook/facebook?hub.mode=subscribe&hub.verify_token={META_VERIFY_TOKEN}&hub.challenge=test_challenge_123")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.text, "test_challenge_123")

    def test_instagram_webhook_handshake(self):
        """Verify Instagram Webhook verification handshake."""
        res = self.client.get(f"/webhook/instagram?hub.mode=subscribe&hub.verify_token={META_VERIFY_TOKEN}&hub.challenge=ig_challenge_789")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.text, "ig_challenge_789")

    def test_instagram_incoming_message(self):
        """Verify incoming Instagram direct message parsing and queueing."""
        ig_payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "IG_ACCOUNT_101",
                    "time": 1700000000,
                    "messaging": [
                        {
                            "sender": {"id": "IG_USER_5544"},
                            "recipient": {"id": "IG_ACCOUNT_101"},
                            "message": {
                                "mid": "ig_mid_12345",
                                "text": "Do you have cotton Churidar in pink?"
                            }
                        }
                    ]
                }
            ]
        }
        res_webhook = self.client.post("/webhook/instagram", json=ig_payload)
        self.assertEqual(res_webhook.status_code, 200)
        self.assertEqual(res_webhook.text, "EVENT_RECEIVED")

    def test_facebook_incoming_message_to_mcp_flow(self):
        """Verify end-to-end Meta Webhook -> MCP Buffer -> Gemini Spark Tool call -> Reply."""
        # 1. Simulate Meta sending an incoming customer message
        meta_payload = {
            "object": "page",
            "entry": [
                {
                    "id": "PAGE_ID_101",
                    "time": 1700000000,
                    "messaging": [
                        {
                            "sender": {"id": "CUST_9988"},
                            "recipient": {"id": "PAGE_ID_101"},
                            "message": {
                                "mid": "mid.12345",
                                "text": "What is the memory protocol for the chatbot?"
                            }
                        }
                    ]
                }
            ]
        }
        res_webhook = self.client.post("/webhook/facebook", json=meta_payload)
        self.assertEqual(res_webhook.status_code, 200)
        self.assertEqual(res_webhook.text, "EVENT_RECEIVED")

        # 2. Gemini Spark executes MCP tool `get_pending_facebook_messages`
        call_payload = {
            "jsonrpc": "2.0",
            "id": "call_1",
            "method": "tools/call",
            "params": {
                "name": "get_pending_facebook_messages",
                "arguments": {"limit": 5}
            }
        }
        res_call = self.client.post("/mcp/messages", json=call_payload)
        self.assertEqual(res_call.status_code, 200)
        data = res_call.json()
        parsed_content = json.loads(data["result"]["content"][0]["text"])
        self.assertGreater(parsed_content["total_pending"], 0)
        
        pending_msg = parsed_content["messages"][-1]
        msg_id = pending_msg["message_id"]
        sender_id = pending_msg["sender_id"]
        self.assertEqual(sender_id, "CUST_9988")

        # 3. Gemini Spark executes MCP tool `search_knowledge_base`
        rag_call_payload = {
            "jsonrpc": "2.0",
            "id": "call_2",
            "method": "tools/call",
            "params": {
                "name": "search_knowledge_base",
                "arguments": {"query": "memory protocol", "top_k": 2}
            }
        }
        res_rag = self.client.post("/mcp/messages", json=rag_call_payload)
        self.assertEqual(res_rag.status_code, 200)
        rag_data = res_rag.json()
        rag_content = json.loads(rag_data["result"]["content"][0]["text"])
        self.assertGreater(rag_content["results_count"], 0)

        # 4. Gemini Spark executes MCP tool `send_facebook_reply`
        reply_call_payload = {
            "jsonrpc": "2.0",
            "id": "call_3",
            "method": "tools/call",
            "params": {
                "name": "send_facebook_reply",
                "arguments": {
                    "message_id": msg_id,
                    "recipient_id": sender_id,
                    "reply_text": "Our multi-tier memory protocol uses fast RAM buffer and SQLite persistent logging."
                }
            }
        }
        res_reply = self.client.post("/mcp/messages", json=reply_call_payload)
        self.assertEqual(res_reply.status_code, 200)
        reply_data = res_reply.json()
        reply_content = json.loads(reply_data["result"]["content"][0]["text"])
        self.assertEqual(reply_content["status"], "delivered")

if __name__ == "__main__":
    unittest.main()
