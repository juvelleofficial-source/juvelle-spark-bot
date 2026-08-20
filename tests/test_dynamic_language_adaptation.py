import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.juvelle_agent import detect_query_language, generate_juvelle_response, generate_juvelle_reply

class TestDynamicLanguageAdaptation(unittest.TestCase):

    def test_voice_message_latin_script_defaults(self):
        """
        Verify voice notes in Malayalam or Hindi default to Latin transliteration
        (Manglish, Hinglish) unless the user explicitly typed in native script previously.
        """
        # Spoken Malayalam transcribed in Malayalam or phonetics -> should detect manglish for voice
        self.assertEqual(detect_query_language("മലയാളത്തിൽ ടോപ്സ് ഉണ്ടോ?", is_voice=True), "manglish")
        self.assertEqual(detect_query_language("ethra divasam edukum?", is_voice=True), "manglish")

        # Spoken Hindi -> should detect hinglish for voice
        self.assertEqual(detect_query_language("क्या आपके पास कॉटन कुर्ती है?", is_voice=True), "hinglish")
        self.assertEqual(detect_query_language("kya price hai bhai?", is_voice=True), "hinglish")

        # Spoken English -> should detect english for voice
        self.assertEqual(detect_query_language("Do you deliver to Kerala?", is_voice=True), "english")

    def test_text_message_native_script_mirroring(self):
        """
        Verify typed text messages in native Unicode scripts are preserved as native script.
        """
        # Typed Malayalam Script -> malayalam_script
        self.assertEqual(detect_query_language("ഡെലിവറി ചാർജ് എത്രയാണ്?", is_voice=False), "malayalam_script")

        # Typed Hindi Devanagari Script -> hindi_script
        self.assertEqual(detect_query_language("क्या आप केरल में डिलीवरी करते हैं?", is_voice=False), "hindi_script")

    def test_text_message_transliteration_mirroring(self):
        """
        Verify typed Latin transliterations (Manglish, Hinglish) are detected properly.
        """
        self.assertEqual(detect_query_language("Keralathil delivery undo?", is_voice=False), "manglish")
        self.assertEqual(detect_query_language("Bhai daily wear tops ka rate kya hai?", is_voice=False), "hinglish")
        self.assertEqual(detect_query_language("Do you have cotton tops?", is_voice=False), "english")

    def test_dynamic_turn_by_turn_switching(self):
        """
        Verify that when a user switches languages across turns, detection adapts immediately.
        """
        history = [
            {"role": "user", "content": "Keralathil delivery undo?"},
            {"role": "assistant", "content": "Athe, Delhivery vazhi 2-3 daysil delivery undu."}
        ]

        # Turn 2: User switches to Hindi / Hinglish
        turn2_lang = detect_query_language("Achha, aur cotton tops ka price kya hai?", history=history)
        self.assertEqual(turn2_lang, "hinglish")

        # Update history with Turn 2
        history.append({"role": "user", "content": "Achha, aur cotton tops ka price kya hai?"})
        history.append({"role": "assistant", "content": "Pure cotton daily wear tops ₹399 se shuru hote hain."})

        # Turn 3: User switches to English
        turn3_lang = detect_query_language("What sizes do you have?", history=history)
        self.assertEqual(turn3_lang, "english")

        # Update history with Turn 3
        history.append({"role": "user", "content": "What sizes do you have?"})
        history.append({"role": "assistant", "content": "We have sizes S to XXL."})

        # Turn 4: User switches to Malayalam Script
        turn4_lang = detect_query_language("ഓർഡർ എങ്ങനെ ചെയ്യണം?", history=history)
        self.assertEqual(turn4_lang, "malayalam_script")

    def test_ambiguous_short_reply_inherits_last_turn(self):
        """
        Verify ambiguous short replies (e.g. 'ok', 's') smoothly inherit the immediately preceding turn.
        """
        history = [
            {"role": "user", "content": "Keralathil delivery undo?"},
            {"role": "assistant", "content": "Athe, Delhivery vazhi 2-3 daysil delivery undu."}
        ]

        # User just replies "ok"
        self.assertEqual(detect_query_language("ok", history=history), "manglish")

if __name__ == "__main__":
    unittest.main()

