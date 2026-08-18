import unittest
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.juvelle_agent import (
    detect_query_language,
    generate_juvelle_response,
    sanitize_manglish_response,
    generate_live_neural_reply
)
from core.audio_processor import (
    check_voice_reply_requested,
    generate_tts_base64
)

class TestJuvellePolyglotRAG(unittest.TestCase):

    def test_detect_query_language_english(self):
        self.assertEqual(detect_query_language("Do you have daily wear cotton tops?"), "english")
        self.assertEqual(detect_query_language("What are the available sizes?"), "english")

    def test_detect_query_language_manglish(self):
        self.assertEqual(detect_query_language("Churidar undo?"), "manglish")
        self.assertEqual(detect_query_language("Price ethraya aanu?"), "manglish")
        self.assertEqual(detect_query_language("Kochi delivery undo?"), "manglish")

    def test_detect_query_language_malayalam_script(self):
        self.assertEqual(detect_query_language("ചുരിദാർ ടോപ്പുകൾ ഉണ്ടോ?"), "malayalam_script")
        self.assertEqual(detect_query_language("എന്താണ് വില?"), "malayalam_script")

    def test_detect_query_language_hinglish(self):
        self.assertEqual(detect_query_language("Kya aapke paas kurti hai?"), "hinglish")
        self.assertEqual(detect_query_language("Price kitna hai bhai?"), "hinglish")
        self.assertEqual(detect_query_language("Cotton top dikhao"), "hinglish")
        self.assertEqual(detect_query_language("Delivery kab tak milegi?"), "hinglish")

    def test_detect_query_language_hindi_script(self):
        self.assertEqual(detect_query_language("क्या आपके पास चूड़ीदार टॉप्स हैं?"), "hindi_script")
        self.assertEqual(detect_query_language("इसकी कीमत क्या है?"), "hindi_script")

    def test_detect_query_language_tanglish(self):
        self.assertEqual(detect_query_language("Kurti irukka?"), "tanglish")
        self.assertEqual(detect_query_language("Price evvalavu sollunga"), "tanglish")
        self.assertEqual(detect_query_language("Chennai delivery irukka?"), "tanglish")

    def test_detect_query_language_tamil_script(self):
        self.assertEqual(detect_query_language("சுடிதார் டாப்ஸ் இருக்கிறதா?"), "tamil_script")
        self.assertEqual(detect_query_language("விலை என்ன?"), "tamil_script")

    def test_detect_query_language_telugu_and_arabic(self):
        self.assertEqual(detect_query_language("హలో! కుర్తీలు ఉన్నాయா?"), "telugu_script")
        self.assertEqual(detect_query_language("مرحبا هل لديكم فساتين؟"), "arabic_script")

    def test_crm_and_history_language_persistence(self):
        history = [
            {"role": "user", "content": "Bhai kurti ka rate kitna hai"},
            {"role": "assistant", "content": "Hey! Rates ₹399 se ₹899 tak hain."}
        ]
        # Ambiguous single word "OK" should persist Hinglish
        lang = detect_query_language("OK", history=history)
        self.assertEqual(lang, "hinglish")

    def test_sanitize_preserves_hinglish_and_native_scripts(self):
        hinglish_text = "Hey! Hum daily wear cotton Churidar tops offer karte hain."
        self.assertEqual(sanitize_manglish_response(hinglish_text, target_language="hinglish"), hinglish_text)
        
        hindi_text = "नमस्ते! हम डेली वियर टॉप्स में स्पेशलाइज करते हैं।"
        self.assertEqual(sanitize_manglish_response(hindi_text, target_language="hindi_script"), hindi_text)

    def test_voice_reply_triggers(self):
        self.assertTrue(check_voice_reply_requested("Please send a voice note"))
        self.assertTrue(check_voice_reply_requested("Voice il parayumo"))
        self.assertTrue(check_voice_reply_requested("Bolke batao please"))
        self.assertTrue(check_voice_reply_requested("Solli anupunga"))
        self.assertFalse(check_voice_reply_requested("Just send photo"))

    def test_polyglot_tts_generation(self):
        # English TTS
        res_en = generate_tts_base64("Welcome to Juvelle", language="english")
        self.assertIsNotNone(res_en)
        self.assertTrue(res_en.startswith("data:audio/mp3;base64,"))

        # Hindi / Hinglish TTS
        res_hi = generate_tts_base64("नमस्ते! Juvelle में आपका स्वागत है।", language="hindi_script")
        self.assertIsNotNone(res_hi)
        self.assertTrue(res_hi.startswith("data:audio/mp3;base64,"))

    def test_generate_juvelle_response_hinglish(self):
        resp = generate_juvelle_response("Kya aapke paas kurti hai?", session_id="test_hinglish_user")
        self.assertIsInstance(resp, list)
        self.assertTrue(len(resp) > 0)
        self.assertIsInstance(resp[0], str)

    def test_generate_juvelle_response_tanglish(self):
        resp = generate_juvelle_response("Kurti irukka?", session_id="test_tanglish_user")
        self.assertIsInstance(resp, list)
        self.assertTrue(len(resp) > 0)
        self.assertIsInstance(resp[0], str)

if __name__ == "__main__":
    unittest.main()
