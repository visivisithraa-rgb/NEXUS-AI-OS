"""
NEXUS AI OS - Day 6 Task: Secure AI API Configuration Tests
Validates:
  1. Status endpoint works without an API key.
  2. Status endpoint reports configuration when temporary test values are provided.
  3. API response NEVER contains the secret test API key.
  4. Missing/whitespace configuration is handled safely without exceptions.
  5. Existing /api/status endpoint remains fully operational.
  6. Existing Notes API functionality remains unbroken.
"""

import os
import json
import sqlite3
import tempfile
import unittest
import importlib

# Import Flask app and modules
import app as backend_app
import ai_config

class TestSecureAIConfig(unittest.TestCase):
    def setUp(self):
        # Save original environment variables to prevent side effects
        self.original_env = {
            "AI_PROVIDER": os.environ.get("AI_PROVIDER"),
            "AI_MODEL": os.environ.get("AI_MODEL"),
            "AI_API_KEY": os.environ.get("AI_API_KEY"),
        }

        # Create isolated temporary directory and test database
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db_path = os.path.join(self.temp_dir.name, "test_nexus.db")
        
        # Initialize minimal SQLite schema for Notes in the test database
        conn = sqlite3.connect(self.test_db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

        # Temporarily redirect app.DB_PATH to the test database
        self.orig_db_path = backend_app.DB_PATH
        backend_app.DB_PATH = self.test_db_path

        # Flask test client
        self.client = backend_app.app.test_client()

    def tearDown(self):
        # Restore database path
        backend_app.DB_PATH = self.orig_db_path

        # Cleanup temporary directory
        self.temp_dir.cleanup()

        # Restore original environment variables
        for key, val in self.original_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def test_01_status_endpoint_without_api_key(self):
        """1. Status endpoint works when no API key is configured."""
        os.environ["AI_PROVIDER"] = "not_configured"
        os.environ.pop("AI_MODEL", None)
        os.environ.pop("AI_API_KEY", None)

        res = self.client.get("/api/ai/status")
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/json", res.content_type)

        data = res.get_json()
        self.assertFalse(data["configured"])
        self.assertEqual(data["provider"], "not_configured")
        self.assertIsNone(data["model"])
        self.assertEqual(data["message"], "AI provider is not configured yet.")

    def test_02_status_endpoint_with_temporary_test_config(self):
        """2. Status endpoint reports configuration when temporary test values are provided."""
        test_provider = "mock_provider"
        test_model = "mock_intelligence_v2"
        test_key = "test_secret_key_abcdef123456"

        os.environ["AI_PROVIDER"] = test_provider
        os.environ["AI_MODEL"] = test_model
        os.environ["AI_API_KEY"] = test_key

        res = self.client.get("/api/ai/status")
        self.assertEqual(res.status_code, 200)

        data = res.get_json()
        self.assertTrue(data["configured"])
        self.assertEqual(data["provider"], test_provider)
        self.assertEqual(data["model"], test_model)
        self.assertEqual(data["message"], "AI configuration is ready.")

    def test_03_api_response_never_exposes_api_key(self):
        """3. API response NEVER contains the test key in keys or values."""
        secret_key = "SUPER_SECRET_TOKEN_DO_NOT_LEAK_9999"
        os.environ["AI_PROVIDER"] = "secure_provider"
        os.environ["AI_MODEL"] = "secure_model"
        os.environ["AI_API_KEY"] = secret_key

        res = self.client.get("/api/ai/status")
        self.assertEqual(res.status_code, 200)

        raw_response_text = res.get_data(as_text=True)
        # Verify secret key is not in the serialized body anywhere
        self.assertNotIn(secret_key, raw_response_text)

        # Verify no secret key attributes exist in response dict
        data = res.get_json()
        self.assertNotIn("AI_API_KEY", data)
        self.assertNotIn("api_key", data)
        self.assertNotIn("key", data)

    def test_04_missing_or_whitespace_configuration_handled_safely(self):
        """4. Missing, blank, or whitespace configuration is handled gracefully."""
        cases = [
            ("", "", ""),
            ("   ", "   ", "   "),
            ("not_configured", "some_model", ""),
            ("custom_provider", "", ""),
        ]

        for prov, mod, key in cases:
            os.environ["AI_PROVIDER"] = prov
            os.environ["AI_MODEL"] = mod
            os.environ["AI_API_KEY"] = key

            res = self.client.get("/api/ai/status")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertFalse(data["configured"])
            self.assertEqual(data["provider"], "not_configured")
            self.assertIsNone(data["model"])
            self.assertEqual(data["message"], "AI provider is not configured yet.")

    def test_05_existing_system_status_endpoint_still_works(self):
        """5. Existing /api/status endpoint still works properly."""
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("system"), "NEXUS AI OS")
        self.assertEqual(data.get("backend"), "Running")
        self.assertEqual(data.get("database"), "Connected")
        self.assertIn("version", data)
        self.assertIn("time", data)

    def test_06_existing_notes_api_unbroken(self):
        """6. Existing Notes API (GET, POST, PUT, DELETE) remains unbroken."""
        # 1. Fetch notes from clean test DB
        get_res = self.client.get("/api/notes")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.get_json(), [])

        # 2. Create note
        post_res = self.client.post("/api/notes", json={"content": "Important architecture note"})
        self.assertEqual(post_res.status_code, 201)
        created_note = post_res.get_json()
        note_id = created_note["id"]
        self.assertEqual(created_note["content"], "Important architecture note")

        # 3. Retrieve note list with new note
        list_res = self.client.get("/api/notes")
        self.assertEqual(list_res.status_code, 200)
        notes = list_res.get_json()
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["id"], note_id)

        # 4. Update note
        put_res = self.client.put(f"/api/notes/{note_id}", json={"content": "Updated architecture note"})
        self.assertEqual(put_res.status_code, 200)

        # 5. Delete note
        del_res = self.client.delete(f"/api/notes/{note_id}")
        self.assertEqual(del_res.status_code, 200)

        # Verify empty again
        final_res = self.client.get("/api/notes")
        self.assertEqual(final_res.get_json(), [])

if __name__ == "__main__":
    unittest.main()
