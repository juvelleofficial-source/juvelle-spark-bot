import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.audio_processor import (
    check_voice_reply_requested,
    generate_tts_base64,
    process_voice_message
)

class TestAudioProcessor(unittest.TestCase):

    def test_voice_reply_triggers(self):
        """Verify voice note trigger detection."""
        self.assertTrue(check_voice_reply_requested("Can you send me a voice message?"))
        self.assertTrue(check_voice_reply_requested("Voice note aayitt parayumo?"))
        self.assertTrue(check_voice_reply_requested("voice reply tharumo"))
        self.assertFalse(check_voice_reply_requested("What is the price of churidar tops?"))
        self.assertFalse(check_voice_reply_requested("Do you ship to Kochi?"))

    def test_tts_generation(self):
        """Verify TTS base64 generation."""
        sample_text = "Welcome to Juvelle Boutique Kerala."
        audio_uri = generate_tts_base64(sample_text, language="english")
        self.assertIsNotNone(audio_uri)
        self.assertTrue(audio_uri.startswith("data:audio/mp3;base64,"))

    def test_process_voice_message_pipeline(self):
        """Verify end-to-end voice message pipeline with valid WAV audio bytes."""
        import wave
        import io

        # Generate a minimal valid 0.5s silent WAV audio
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(b'\x00' * 16000)
        valid_wav_bytes = buf.getvalue()

        result = process_voice_message(
            audio_bytes=valid_wav_bytes,
            mime_type="audio/wav",
            session_id="test_voice_session"
        )
        self.assertIn("transcript", result)
        self.assertIn("reply_text", result)
        self.assertIn("has_audio_reply", result)
        self.assertEqual(result["session_id"], "test_voice_session")

if __name__ == "__main__":
    unittest.main()
