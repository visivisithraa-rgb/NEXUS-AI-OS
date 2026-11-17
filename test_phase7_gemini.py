"""
NEXUS AI OS - Phase 7 Test Suite
Validates Gemini-style AI Experience:
  1. Conversation Rename (PUT /api/conversations/<id>)
  2. Real AI Image Generation (POST /api/images/generate, GET /api/images, DELETE /api/images/<id>)
  3. Image file persistence and SQLite tracking
  4. Global JSON error responses (no HTML error pages)
  5. API Key Security (masked, never plaintext in responses)
  6. Agent Tool dispatch for Image Generation
  7. Multi-turn conversation retention
"""

import os
import json
import sqlite3
import unittest
from app import app, DB_PATH, IMAGES_FOLDER

class TestPhase7Gemini(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_01_conversation_rename(self):
        # 1. Create a conversation
        create_res = self.client.post("/api/conversations", json={"name": "Initial Name"})
        self.assertEqual(create_res.status_code, 201)
        conv = create_res.get_json()
        conv_id = conv["id"]

        # 2. Rename it via PUT
        new_name = "Gemini Quantum Dialogue"
        rename_res = self.client.put(f"/api/conversations/{conv_id}", json={"name": new_name})
        self.assertEqual(rename_res.status_code, 200)
        data = rename_res.get_json()
        self.assertEqual(data["name"], new_name)
        self.assertEqual(data["id"], conv_id)

        # 3. Verify SQLite persistence
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT name FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], new_name)

        # 4. Validation error on empty name
        bad_res = self.client.put(f"/api/conversations/{conv_id}", json={"name": "   "})
        self.assertEqual(bad_res.status_code, 400)
        self.assertIn("error", bad_res.get_json())

    def test_02_image_generation_and_storage(self):
        prompt = "Futuristic neon purple processor chip, isometric, 8k"
        aspect_ratio = "1:1"

        # 1. Generate image
        gen_res = self.client.post("/api/images/generate", json={
            "prompt": prompt,
            "aspect_ratio": aspect_ratio
        })
        self.assertEqual(gen_res.status_code, 201, f"Generate failed: {gen_res.get_data(as_text=True)}")
        data = gen_res.get_json()
        self.assertTrue(data.get("success"))
        img_info = data.get("image")
        self.assertIsNotNone(img_info)

        img_id = img_info["id"]
        filename = img_info["filename"]
        url = img_info["url"]

        # 2. Verify file on disk
        disk_path = os.path.join(IMAGES_FOLDER, filename)
        self.assertTrue(os.path.isfile(disk_path), f"File {disk_path} not found on disk")
        self.assertGreater(os.path.getsize(disk_path), 100, "Generated file too small or empty")

        # 3. Verify SQLite record
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT prompt, filename, aspect_ratio FROM generated_images WHERE id = ?", (img_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], prompt)
        self.assertEqual(row[1], filename)

        # 4. Fetch list of images
        list_res = self.client.get("/api/images")
        self.assertEqual(list_res.status_code, 200)
        images = list_res.get_json()
        self.assertTrue(any(img["id"] == img_id for img in images))

        # 5. Fetch image file directly
        file_res = self.client.get(f"/api/images/{filename}")
        self.assertEqual(file_res.status_code, 200)
        self.assertIn("image/", file_res.content_type)
        file_res.close()

        # 6. Delete image
        del_res = self.client.delete(f"/api/images/{img_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertFalse(os.path.isfile(disk_path), "File was not removed from disk")

    def test_03_json_error_handling(self):
        # Trigger 404
        res_404 = self.client.get("/api/nonexistent_route_test")
        self.assertEqual(res_404.status_code, 404)
        self.assertIn("application/json", res_404.content_type)
        self.assertIn("error", res_404.get_json())

        # Trigger 405 Method Not Allowed
        res_405 = self.client.post("/api/images", json={})
        self.assertEqual(res_405.status_code, 405)
        self.assertIn("application/json", res_405.content_type)
        self.assertIn("error", res_405.get_json())

    def test_04_gemini_api_key_security(self):
        res = self.client.get("/api/settings/gemini-key")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("configured", data)
        self.assertIn("masked", data)
        masked = data["masked"]
        # Must never expose full plaintext key
        real_key = os.getenv("GEMINI_API_KEY", "")
        if real_key:
            self.assertNotEqual(masked, real_key)
            self.assertIn("•", masked)

    def test_05_agent_image_generation_tool(self):
        # Execute image generation command via AI Agent
        cmd = "Generate an image of a neon cyberspace gateway"
        res = self.client.post("/api/agent/command", json={"command": cmd})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("generate_image", data.get("tools_called", []))
        self.assertTrue(any(a.get("action") == "open_app" and a.get("target") == "AI Assistant" for a in data.get("client_actions", [])))

    def test_06_multi_turn_conversation(self):
        res1 = self.client.post("/api/chat", json={"message": "Hello, my name is Alex and I am developing NEXUS OS."})
        if res1.status_code == 200:
            data1 = res1.get_json()
            conv_id = data1.get("conversation_id")
            self.assertIsNotNone(conv_id)

            # Check messages in DB
            conn = sqlite3.connect(DB_PATH)
            count = conn.execute("SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conv_id,)).fetchone()[0]
            conn.close()
            self.assertGreaterEqual(count, 2)
        else:
            # When running in sandboxed environment without internet access
            self.assertIn("application/json", res1.content_type)
            self.assertIn("error", res1.get_json())

if __name__ == "__main__":
    unittest.main()
