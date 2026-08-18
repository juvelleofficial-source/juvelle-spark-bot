import unittest
from fastapi.testclient import TestClient
from api.main import app
from core.juvelle_agent import generate_juvelle_response

class TestInstagramTesterIntegration(unittest.TestCase):
    """
    Comprehensive Unit & Integration tests for Instagram Tester Webhooks and Juvelle Agent.
    """

    def setUp(self):
        self.client = TestClient(app)

    def test_01_static_tester_mount_serves_html(self):
        """Verify that /tester serves the Instagram Tester HTML"""
        response = self.client.get("/tester/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Juvelle", response.text)

    def test_02_static_tester_serves_config(self):
        """Verify that /tester/config.json returns valid configuration"""
        response = self.client.get("/tester/config.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("webhook_url", data)
        self.assertIn("127.0.0.1:8000", data["webhook_url"])

    def test_03_webhook_greeting_query(self):
        """Verify greeting query returns welcome response"""
        payload = {"chatInput": "Hi", "sessionId": "unit_test_01"}
        response = self.client.post("/webhook/instagram-test", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("output", data)
        output = data["output"]
        self.assertTrue(any("Juvelle" in msg or "Welcome" in msg for msg in output))

    def test_04_webhook_kerala_only_restriction(self):
        """Verify outside Kerala requests are politely declined"""
        payload = {"chatInput": "Do you deliver to Bangalore or Mumbai?", "sessionId": "unit_test_02"}
        response = self.client.post("/webhook/instagram-test", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        output_str = " ".join(data["output"])
        self.assertIn("Kerala", output_str)

    def test_05_webhook_no_cod_policy(self):
        """Verify COD requests clearly state online payment only"""
        payload = {"chatInput": "Can I pay with Cash on Delivery?", "sessionId": "unit_test_03"}
        response = self.client.post("/webhook/instagram-test", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        output_str = " ".join(data["output"])
        self.assertTrue("online" in output_str.lower() or "gpay" in output_str.lower() or "upi" in output_str.lower())

    def test_06_webhook_legacy_n8n_path(self):
        """Verify legacy /webhook/ed03d435-639b-4018-b0be-829891736771 endpoint works identically"""
        payload = {"chatInput": "What is the price of tops?", "sessionId": "unit_test_04"}
        response = self.client.post("/webhook/ed03d435-639b-4018-b0be-829891736771", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        output_str = " ".join(data["output"])
        self.assertIn("₹", output_str)

    def test_07_form_data_payload_support(self):
        """Verify form-data submission works for simulated voice / file uploads"""
        response = self.client.post(
            "/webhook/instagram-test",
            data={"chatInput": "[Voice Message]", "sessionId": "unit_test_voice"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("output", data)

if __name__ == "__main__":
    unittest.main()
