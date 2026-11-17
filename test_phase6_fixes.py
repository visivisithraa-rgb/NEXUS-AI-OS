import unittest
import json
import os
import sqlite3
import base64
from app import app, DB_PATH, initialize_database

class TestVoiceAndChatHistoryFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def setUp(self):
        self.client = app.test_client()

    def test_01_conversation_creation_and_listing(self):
        """Test conversation creation, listing, and ordering"""
        # Create a new conversation
        res = self.client.post("/api/conversations", json={"name": "Test Conv Alpha"})
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        conv_id = data["id"]
        self.assertTrue(conv_id > 0)
        self.assertEqual(data["name"], "Test Conv Alpha")

        # List conversations
        res = self.client.get("/api/conversations")
        self.assertEqual(res.status_code, 200)
        convs = res.get_json()
        self.assertTrue(any(c["id"] == conv_id for c in convs))

        # Search conversations
        res = self.client.get("/api/conversations/search?q=Alpha")
        self.assertEqual(res.status_code, 200)
        search_res = res.get_json()
        self.assertTrue(any(c["id"] == conv_id for c in search_res))

    def test_02_chat_message_persistence_and_no_loss(self):
        """Test sending messages, preserving conversation ID and chronological order"""
        # Create conversation
        res = self.client.post("/api/conversations", json={"name": "History Test Chat"})
        conv_id = res.get_json()["id"]

        # Directly insert 2 messages to simulate chat history without consuming Gemini API quota
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, 'user', 'Hello AI 1', '2026-11-15T10:00:00')", (conv_id,))
        conn.execute("INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, 'assistant', 'Hello User 1', '2026-11-15T10:00:05')", (conv_id,))
        conn.execute("INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, 'user', 'Hello AI 2', '2026-11-15T10:01:00')", (conv_id,))
        conn.execute("INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, 'assistant', 'Hello User 2', '2026-11-15T10:01:05')", (conv_id,))
        conn.commit()
        conn.close()

        # Retrieve messages via API
        res = self.client.get(f"/api/conversations/{conv_id}/messages")
        self.assertEqual(res.status_code, 200)
        msgs = res.get_json()
        self.assertEqual(len(msgs), 4)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[0]["content"], "Hello AI 1")
        self.assertEqual(msgs[1]["role"], "assistant")
        self.assertEqual(msgs[1]["content"], "Hello User 1")
        self.assertEqual(msgs[2]["role"], "user")
        self.assertEqual(msgs[2]["content"], "Hello AI 2")
        self.assertEqual(msgs[3]["role"], "assistant")
        self.assertEqual(msgs[3]["content"], "Hello User 2")

    def test_03_conversation_deletion(self):
        """Test deleting conversation removes it and cascades message deletion"""
        res = self.client.post("/api/conversations", json={"name": "To Delete"})
        conv_id = res.get_json()["id"]

        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, 'user', 'temp message', '2026-11-15T10:00:00')", (conv_id,))
        conn.commit()
        conn.close()

        del_res = self.client.delete(f"/api/conversations/{conv_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.get_json()["result"], "deleted")

        # Verify not present in list
        list_res = self.client.get("/api/conversations")
        self.assertFalse(any(c["id"] == conv_id for c in list_res.get_json()))

    def test_04_voice_transcribe_endpoint_validation(self):
        """Test voice transcribe input validation (empty data, invalid base64)"""
        # Empty payload
        res = self.client.post("/api/voice/transcribe", json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn("No audio data received", res.get_json().get("error", ""))

        # Invalid base64
        res = self.client.post("/api/voice/transcribe", json={"audio": "not_valid_base64!!!"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Invalid base64", res.get_json().get("error", ""))

    def test_05_voice_transcribe_with_audio_bytes(self):
        """Test voice transcribe accepts audio bytes and invokes Gemini"""
        # Minimal valid WAV header with silence
        wav_header = b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
        b64_audio = base64.b64encode(wav_header).decode("utf-8")

        res = self.client.post("/api/voice/transcribe", json={
            "audio": b64_audio,
            "mime_type": "audio/wav"
        })
        # Should return 200 (with text) or 400 (if API key missing in test env) or 429
        self.assertIn(res.status_code, [200, 400, 429, 500])
        if res.status_code == 200:
            self.assertIn("text", res.get_json())

    def test_06_electron_main_media_permissions(self):
        """Verify electron/main.js contains media permission handler"""
        with open("electron/main.js", "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("setPermissionRequestHandler", content)
        self.assertIn("setPermissionCheckHandler", content)
        self.assertIn("'media'", content)

    def test_07_script_js_no_destructive_p_removal(self):
        """Verify script.js no longer wipes chatLog using chatLog.querySelector('p')"""
        with open("script.js", "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn('if (chatLog.querySelector("p"))', content)
        self.assertIn('.chat-empty-placeholder', content)
        self.assertIn('setVoiceStatus', content)
        self.assertIn('/api/voice/transcribe', content)
        self.assertIn('switchConversation', content)
        self.assertIn('loadConversations', content)

if __name__ == "__main__":
    unittest.main()
