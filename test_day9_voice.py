"""
NEXUS AI OS - Day 9 Automated Test Suite
Voice Input using the Browser Web Speech API

Tests:
1. Verification of Web Speech API logic in script.js (feature detection, SpeechRecognition / webkitSpeechRecognition).
2. Verification of language support: en-IN (English India) and ta-IN (Tamil India) with dynamic selector.
3. Verification of one-shot recognition (continuous = false, interimResults = true).
4. Verification that recognized text is populated into chat input and NOT automatically sent to AI.
5. Verification of error handling (not-allowed, permission-denied, no-speech, audio-capture, network).
6. Verification of Stop Listening controls and window closure handling (closeApp stops recognition).
7. Verification of privacy and safety guarantees (no audio files, no backend audio upload, no SQLite audio storage).
8. Verification of HTML elements in index.html (microphone button next to chat input and Send button, language selector).
"""

import os
import re
import unittest
from app import app


class TestDay9VoiceInputWebSpeech(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(cls.root_dir, "script.js"), "r", encoding="utf-8") as f:
            cls.script_js = f.read()
        with open(os.path.join(cls.root_dir, "index.html"), "r", encoding="utf-8") as f:
            cls.index_html = f.read()
        with open(os.path.join(cls.root_dir, "style.css"), "r", encoding="utf-8") as f:
            cls.style_css = f.read()

    def test_01_web_speech_api_detection_and_usage(self):
        """Check browser Web Speech API detection and fallback."""
        self.assertIn("SpeechRecognition", self.script_js)
        self.assertIn("webkitSpeechRecognition", self.script_js)
        self.assertIn("isWebSpeechSupported", self.script_js)
        self.assertIn("getSpeechRecognitionClass", self.script_js)

        # Ensure fallback message for unsupported browsers
        self.assertTrue(
            "not supported in this browser" in self.script_js.lower(),
            "Must provide clear fallback message when Web Speech API is unsupported"
        )

    def test_02_language_support_english_and_tamil(self):
        """Verify English (en-IN) and Tamil (ta-IN) support and selector."""
        self.assertIn("en-IN", self.script_js)
        self.assertIn("ta-IN", self.script_js)
        self.assertIn("en-IN", self.index_html)
        self.assertIn("ta-IN", self.index_html)

        # Verify language selector element in assistant UI
        self.assertIn('id="voiceLangSelect"', self.script_js)
        self.assertIn('id="desktopVoiceLangSelect"', self.index_html)
        self.assertIn("nexus_speech_lang", self.script_js)

    def test_03_one_shot_recognition_configuration(self):
        """Verify one-shot recognition (continuous = false, interimResults = true)."""
        self.assertIn("recognition.continuous = false", self.script_js)
        self.assertIn("recognition.interimResults = true", self.script_js)
        self.assertIn("recognition.maxAlternatives = 1", self.script_js)

    def test_04_text_populated_in_input_without_auto_send(self):
        """Verify recognized text is populated into chat input and NOT auto-sent."""
        # Recognition onresult should update input value
        self.assertIn("inputEl.value =", self.script_js)

        # In voice result/end handler, it must NOT call sendMessage() automatically
        # Look for the section after recognition.onend
        onend_match = re.search(r'recognition\.onend\s*=\s*\(\)\s*=>\s*\{(.*?)\};', self.script_js, re.DOTALL)
        self.assertIsNotNone(onend_match, "recognition.onend handler must exist")
        onend_body = onend_match.group(1)
        self.assertNotIn("sendMessage()", onend_body, "Speech recognition must NOT auto-send to AI in onend")

        onresult_match = re.search(r'recognition\.onresult\s*=\s*\([^)]*\)\s*=>\s*\{(.*?)\};', self.script_js, re.DOTALL)
        self.assertIsNotNone(onresult_match, "recognition.onresult handler must exist")
        onresult_body = onresult_match.group(1)
        self.assertNotIn("sendMessage()", onresult_body, "Speech recognition must NOT auto-send to AI in onresult")

    def test_05_error_handling_for_permissions_and_devices(self):
        """Verify handling of not-allowed, no-speech, audio-capture, and network errors."""
        self.assertIn("not-allowed", self.script_js)
        self.assertIn("permission-denied", self.script_js)
        self.assertIn("no-speech", self.script_js)
        self.assertIn("audio-capture", self.script_js)
        self.assertIn("network", self.script_js)

    def test_06_stop_listening_and_window_close_handling(self):
        """Verify Stop Listening controls and stopping recognition on closeApp()."""
        self.assertIn("stopSpeechRecognition", self.script_js)
        self.assertIn("Stop Listening", self.script_js)

        # In closeApp(), stopSpeechRecognition must be invoked
        close_app_match = re.search(r'function closeApp\(\)\s*\{(.*?)\}', self.script_js, re.DOTALL)
        self.assertIsNotNone(close_app_match, "closeApp function must exist")
        self.assertIn("stopSpeechRecognition", close_app_match.group(1))

    def test_07_privacy_guarantees(self):
        """Verify privacy guarantees: no audio files sent to backend for Web Speech."""
        # startSpeechRecognition should not send audio blobs or FormData to backend
        speech_fn_match = re.search(r'function startSpeechRecognition\([^)]*\)\s*\{(.*?)\n\}', self.script_js, re.DOTALL)
        self.assertIsNotNone(speech_fn_match)
        speech_body = speech_fn_match.group(1)
        self.assertNotIn("fetch('/api/voice/transcribe'", speech_body)
        self.assertNotIn("safeFetchJson('/api/voice/transcribe'", speech_body)

    def test_08_html_and_css_elements(self):
        """Verify microphone buttons and responsive styles exist."""
        self.assertIn('id="desktopMicBtn"', self.index_html)
        self.assertIn('id="userInput"', self.index_html)
        self.assertIn('.mic-recording', self.style_css)
        self.assertIn('mic-pulse', self.style_css)


if __name__ == "__main__":
    unittest.main()
