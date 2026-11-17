"""
NEXUS AI OS - Day 10 Automated Test Suite
Test, Debug and Stabilize Voice Input

Tests:
1. Multi-click & Duplicate Session Prevention (isStartingSpeech guard).
2. Stuck-State Prevention & Safety Watchdog (voiceWatchdogTimer resets active listening).
3. Text Preservation (already typed text is preserved with proper spacing, not erased).
4. Error Handling Coverage (not-allowed, permission-denied, no-speech, audio-capture, network, service-not-allowed, language-not-supported, bad-grammar).
5. Window Lifecycle & Tab Switch Hooks (closeApp and switchAssistantTab stop recognition).
6. Dual Language Selection & Bidirectional Synchronization (en-IN and ta-IN).
7. Review Before Sending (recognition callbacks never auto-send to AI).
8. Privacy & Safety Protections (no audio saving, no backend upload, no shell execution).
"""

import os
import re
import unittest
from app import app


class TestDay10VoiceStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(cls.root_dir, "script.js"), "r", encoding="utf-8") as f:
            cls.script_js = f.read()
        with open(os.path.join(cls.root_dir, "index.html"), "r", encoding="utf-8") as f:
            cls.index_html = f.read()

    def test_01_multi_click_guard(self):
        """1. Prevent duplicate recognition sessions from rapid repeated clicks."""
        self.assertIn("isStartingSpeech", self.script_js)
        # Verify guard in toggleSpeechRecognition
        toggle_fn_match = re.search(r'function toggleSpeechRecognition\([^)]*\)\s*\{(.*?)\n\}', self.script_js, re.DOTALL)
        self.assertIsNotNone(toggle_fn_match)
        toggle_body = toggle_fn_match.group(1)
        self.assertIn("if (isStartingSpeech)", toggle_body, "Must guard against duplicate sessions when isStartingSpeech is true")

    def test_02_safety_watchdog_timeout(self):
        """2. Ensure microphone status does not remain stuck on Listening."""
        self.assertIn("voiceWatchdogTimer", self.script_js)
        self.assertIn("clearTimeout(voiceWatchdogTimer)", self.script_js)
        self.assertIn("setTimeout", self.script_js)

    def test_03_existing_text_preservation(self):
        """3. Text already typed by user is preserved and appended cleanly."""
        self.assertIn("existingText", self.script_js)
        # Verify prefix space handling and restoration on abort
        self.assertTrue(
            "existingText.endsWith(' ')" in self.script_js or "prefix" in self.script_js,
            "Must handle spacing cleanly when user already typed text"
        )
        self.assertIn("inputEl.value = existingText", self.script_js, "Must restore existing text if speech produced no words")

    def test_04_comprehensive_error_handling(self):
        """4. Display helpful messages for all speech recognition error states."""
        required_errors = [
            "not-allowed",
            "permission-denied",
            "no-speech",
            "audio-capture",
            "network",
            "service-not-allowed",
            "language-not-supported",
            "bad-grammar"
        ]
        for err in required_errors:
            self.assertIn(err, self.script_js, f"Error state '{err}' must be explicitly handled")

    def test_05_window_close_and_tab_switch_hooks(self):
        """5. Closing assistant or switching tabs stops active recognition."""
        close_app_match = re.search(r'function closeApp\(\)\s*\{(.*?)\n\}', self.script_js, re.DOTALL)
        self.assertIsNotNone(close_app_match)
        self.assertIn("stopSpeechRecognition", close_app_match.group(1))

        tab_switch_match = re.search(r'function switchAssistantTab\([^)]*\)\s*\{(.*?)\n\}', self.script_js, re.DOTALL)
        self.assertIsNotNone(tab_switch_match)
        self.assertIn("stopSpeechRecognition", tab_switch_match.group(1))

    def test_06_bidirectional_language_sync(self):
        """6. English and Tamil language selector supports bidirectional synchronization."""
        self.assertIn("voiceLangSelect", self.script_js)
        self.assertIn("desktopVoiceLangSelect", self.script_js)
        self.assertIn("en-IN", self.script_js)
        self.assertIn("ta-IN", self.script_js)

    def test_07_no_auto_send_to_ai(self):
        """7. Speech is never automatically sent to the AI without user review."""
        onresult_match = re.search(r'recognition\.onresult\s*=\s*\([^)]*\)\s*=>\s*\{(.*?)\};', self.script_js, re.DOTALL)
        self.assertIsNotNone(onresult_match)
        self.assertNotIn("sendMessage()", onresult_match.group(1))

        onend_match = re.search(r'recognition\.onend\s*=\s*\(\)\s*=>\s*\{(.*?)\};', self.script_js, re.DOTALL)
        self.assertIsNotNone(onend_match)
        self.assertNotIn("sendMessage()", onend_match.group(1))

    def test_08_privacy_and_security(self):
        """8. No microphone audio saved to files or sent as raw audio to Flask/SQLite."""
        speech_fn_match = re.search(r'function startSpeechRecognition\([^)]*\)\s*\{(.*?)\n\}', self.script_js, re.DOTALL)
        self.assertIsNotNone(speech_fn_match)
        speech_body = speech_fn_match.group(1)
        self.assertNotIn("POST", speech_body)
        self.assertNotIn("FormData", speech_body)
        self.assertNotIn("fetch('/api/voice/transcribe'", speech_body)


if __name__ == "__main__":
    unittest.main()
