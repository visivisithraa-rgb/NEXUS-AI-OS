"""
NEXUS AI OS - Day 8 Automated Test Suite
Persistent AI Chat History using SQLite

Tests:
1. GET /api/chat/history with no messages (returns empty list).
2. Save conversation (storing user and assistant messages in chat_messages).
3. Retrieve both user and assistant messages via GET /api/chat/history.
4. Verify chronological order of retrieved messages.
5. Verify limit parameter handling (default 50, custom limit, invalid limit).
6. Verify database error handling (safe JSON returned, no crash or secret leaks).
7. Mocked AI responses saved properly in chat_messages on POST /api/chat.
8. Failed AI requests do NOT create fake assistant responses in chat_messages.
"""

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import app as nexus_app
from app import app, initialize_database


class TestChatHistorySQLite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary directory for test database
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.orig_db_path = nexus_app.DB_PATH
        cls.test_db_path = os.path.join(cls.temp_dir.name, "test_nexus.db")
        nexus_app.DB_PATH = cls.test_db_path
        initialize_database()

    @classmethod
    def tearDownClass(cls):
        nexus_app.DB_PATH = cls.orig_db_path
        cls.temp_dir.cleanup()

    def setUp(self):
        self.client = app.test_client()
        # Clean chat_messages table between tests
        conn = sqlite3.connect(nexus_app.DB_PATH)
        conn.execute("DELETE FROM chat_messages")
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM conversations")
        conn.commit()
        conn.close()

    def test_01_get_history_empty(self):
        """1. GET /api/chat/history with no messages returns empty list."""
        res = self.client.get("/api/chat/history")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, dict)
        self.assertIn("messages", data)
        self.assertEqual(data["messages"], [])

    def test_02_save_conversation(self):
        """2. Save conversation storing user and assistant messages in SQLite chat_messages."""
        conn = sqlite3.connect(nexus_app.DB_PATH)
        conn.execute(
            "INSERT INTO chat_messages (role, message, created_at) VALUES ('user', ?, ?)",
            ("Hello NEXUS", "2026-11-15 10:00:00")
        )
        conn.execute(
            "INSERT INTO chat_messages (role, message, created_at) VALUES ('assistant', ?, ?)",
            ("Hello! How can I assist you?", "2026-11-15 10:00:02")
        )
        conn.commit()

        # Verify rows in database
        rows = conn.execute("SELECT id, role, message, created_at FROM chat_messages ORDER BY id ASC").fetchall()
        conn.close()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], "user")
        self.assertEqual(rows[0][2], "Hello NEXUS")
        self.assertEqual(rows[0][3], "2026-11-15 10:00:00")
        self.assertEqual(rows[1][1], "assistant")
        self.assertEqual(rows[1][2], "Hello! How can I assist you?")
        self.assertEqual(rows[1][3], "2026-11-15 10:00:02")

    def test_03_retrieve_both_user_and_assistant_messages(self):
        """3. Retrieve both user and assistant messages via GET /api/chat/history."""
        conn = sqlite3.connect(nexus_app.DB_PATH)
        conn.execute(
            "INSERT INTO chat_messages (role, message, created_at) VALUES ('user', ?, ?)",
            ("What is quantum computing?", "2026-11-15 10:10:00")
        )
        conn.execute(
            "INSERT INTO chat_messages (role, message, created_at) VALUES ('assistant', ?, ?)",
            ("Quantum computing uses qubits to process information.", "2026-11-15 10:10:05")
        )
        conn.commit()
        conn.close()

        res = self.client.get("/api/chat/history")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        messages = data.get("messages", [])
        self.assertEqual(len(messages), 2)

        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["message"], "What is quantum computing?")
        self.assertEqual(messages[0]["created_at"], "2026-11-15 10:10:00")

        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["message"], "Quantum computing uses qubits to process information.")
        self.assertEqual(messages[1]["created_at"], "2026-11-15 10:10:05")

    def test_04_verify_chronological_order(self):
        """4. Verify chronological order of retrieved messages."""
        timestamps = [
            ("user", "Question 1", "2026-11-15 11:00:00"),
            ("assistant", "Answer 1", "2026-11-15 11:00:05"),
            ("user", "Question 2", "2026-11-15 11:01:00"),
            ("assistant", "Answer 2", "2026-11-15 11:01:06"),
            ("user", "Question 3", "2026-11-15 11:02:00"),
            ("assistant", "Answer 3", "2026-11-15 11:02:07"),
        ]

        conn = sqlite3.connect(nexus_app.DB_PATH)
        for role, msg, ts in timestamps:
            conn.execute(
                "INSERT INTO chat_messages (role, message, created_at) VALUES (?, ?, ?)",
                (role, msg, ts)
            )
        conn.commit()
        conn.close()

        res = self.client.get("/api/chat/history")
        self.assertEqual(res.status_code, 200)
        messages = res.get_json().get("messages", [])
        self.assertEqual(len(messages), 6)

        # Check strict chronological order
        for i in range(len(messages)):
            self.assertEqual(messages[i]["role"], timestamps[i][0])
            self.assertEqual(messages[i]["message"], timestamps[i][1])
            self.assertEqual(messages[i]["created_at"], timestamps[i][2])

    def test_05_verify_limit_parameter(self):
        """5. Verify limit parameter handling (default 50, custom limit, invalid limit)."""
        conn = sqlite3.connect(nexus_app.DB_PATH)
        for i in range(1, 11):
            role = "user" if i % 2 != 0 else "assistant"
            conn.execute(
                "INSERT INTO chat_messages (role, message, created_at) VALUES (?, ?, ?)",
                (role, f"Message {i}", f"2026-11-15 12:00:{i:02d}")
            )
        conn.commit()
        conn.close()

        # Custom limit = 4 (should return latest 4 messages in chronological order: 7, 8, 9, 10)
        res = self.client.get("/api/chat/history?limit=4")
        self.assertEqual(res.status_code, 200)
        messages = res.get_json().get("messages", [])
        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[0]["message"], "Message 7")
        self.assertEqual(messages[1]["message"], "Message 8")
        self.assertEqual(messages[2]["message"], "Message 9")
        self.assertEqual(messages[3]["message"], "Message 10")

        # Default limit (returns all 10 since 10 < 50)
        res_default = self.client.get("/api/chat/history")
        self.assertEqual(res_default.status_code, 200)
        self.assertEqual(len(res_default.get_json().get("messages", [])), 10)

        # Invalid limit query param falls back safely to default
        res_invalid = self.client.get("/api/chat/history?limit=invalid_value")
        self.assertEqual(res_invalid.status_code, 200)
        self.assertEqual(len(res_invalid.get_json().get("messages", [])), 10)

        res_negative = self.client.get("/api/chat/history?limit=-10")
        self.assertEqual(res_negative.status_code, 200)
        self.assertEqual(len(res_negative.get_json().get("messages", [])), 10)

    def test_06_verify_database_error_handling(self):
        """6. Verify database error handling returns safe JSON without crashing or leaking secrets."""
        # Intentionally point to an invalid database path that cannot be accessed
        invalid_db_path = os.path.join(self.temp_dir.name, "nonexistent_dir", "deep", "invalid.db")
        orig = nexus_app.DB_PATH
        nexus_app.DB_PATH = invalid_db_path

        try:
            res = self.client.get("/api/chat/history")
            self.assertEqual(res.status_code, 500)
            data = res.get_json()
            self.assertIsInstance(data, dict)
            self.assertIn("messages", data)
            self.assertEqual(data["messages"], [])
            self.assertIn("error", data)
            # Ensure error does not leak raw paths, credentials, or secrets
            self.assertNotIn("GEMINI_API_KEY", str(data))
            self.assertNotIn("password", str(data).lower())
        finally:
            nexus_app.DB_PATH = orig

    @patch("app.get_gemini_model")
    def test_07_mocked_ai_responses_saved_properly(self, mock_get_model):
        """7. Mocked AI responses saved properly in chat_messages on POST /api/chat."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Quantum computing uses superposition and entanglement."
        mock_model.generate_content.return_value = mock_response
        mock_get_model.return_value = (mock_model, None)

        user_query = "Explain quantum computing briefly."
        res = self.client.post("/api/chat", json={"message": user_query})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["reply"], "Quantum computing uses superposition and entanglement.")

        # Check SQLite chat_messages table
        conn = sqlite3.connect(nexus_app.DB_PATH)
        rows = conn.execute("SELECT role, message FROM chat_messages ORDER BY id ASC").fetchall()
        conn.close()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "user")
        self.assertEqual(rows[0][1], user_query)
        self.assertEqual(rows[1][0], "assistant")
        self.assertEqual(rows[1][1], "Quantum computing uses superposition and entanglement.")

        # Verify via GET /api/chat/history
        hist_res = self.client.get("/api/chat/history")
        self.assertEqual(hist_res.status_code, 200)
        hist_msgs = hist_res.get_json().get("messages", [])
        self.assertEqual(len(hist_msgs), 2)
        self.assertEqual(hist_msgs[0]["role"], "user")
        self.assertEqual(hist_msgs[0]["message"], user_query)
        self.assertEqual(hist_msgs[1]["role"], "assistant")
        self.assertEqual(hist_msgs[1]["message"], "Quantum computing uses superposition and entanglement.")

    @patch("app.get_gemini_model")
    def test_08_failed_ai_requests_do_not_create_fake_assistant_responses(self, mock_get_model):
        """8. Failed AI requests do NOT create fake assistant responses in chat_messages."""
        # Case A: Missing API key / model failure
        mock_get_model.return_value = (None, "missing_key")

        res = self.client.post("/api/chat", json={"message": "Hello when AI is broken"})
        self.assertIn(res.status_code, [400, 500, 503])
        self.assertIn("error", res.get_json())

        # Verify in SQLite: NO assistant message was created
        conn = sqlite3.connect(nexus_app.DB_PATH)
        asst_rows = conn.execute("SELECT id, role, message FROM chat_messages WHERE role = 'assistant'").fetchall()
        conn.close()
        self.assertEqual(len(asst_rows), 0, "No assistant message should be inserted when AI fails")

        # Case B: AI API throws an exception during generation
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("Google Gemini 503: Service Unavailable")
        mock_get_model.return_value = (mock_model, None)

        res2 = self.client.post("/api/chat", json={"message": "Another failing query"})
        self.assertEqual(res2.status_code, 500)
        self.assertIn("error", res2.get_json())

        # Verify again in SQLite: still NO assistant message was created
        conn = sqlite3.connect(nexus_app.DB_PATH)
        asst_rows2 = conn.execute("SELECT id, role, message FROM chat_messages WHERE role = 'assistant'").fetchall()
        conn.close()
        self.assertEqual(len(asst_rows2), 0, "Fake assistant response must NEVER be created on failure")


if __name__ == "__main__":
    unittest.main()
