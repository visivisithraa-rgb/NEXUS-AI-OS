"""
NEXUS AI OS - Day 12 Automated Test Suite
Indexed Documents Library & Secure Removal

Tests:
1. List indexed documents when empty (GET /api/files/list).
2. Index documents and verify correct document count.
3. Verify correct filenames, IDs, and indexed_at timestamps.
4. Refresh the library (consistent idempotent listing).
5. Reject deletion without confirmation (HTTP 400).
6. Remove an indexed record with confirmation (HTTP 200).
7. Verify the original file still exists on disk after index removal.
8. Verify the removed document no longer appears in search results.
9. Verify other indexed documents remain intact in index and search.
10. Test deletion with JSON confirmation payload and reject invalid document IDs.
"""

import io
import os
import sqlite3
import tempfile
import unittest

import app as nexus_app
from app import app, initialize_database


class TestIndexedDocumentsLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary directory for test database and files
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.orig_db_path = nexus_app.DB_PATH
        cls.test_db_path = os.path.join(cls.temp_dir.name, "test_nexus.db")
        nexus_app.DB_PATH = cls.test_db_path
        initialize_database()
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        nexus_app.DB_PATH = cls.orig_db_path
        cls.temp_dir.cleanup()

    def setUp(self):
        # Clean indexed_documents table before each test
        conn = sqlite3.connect(nexus_app.DB_PATH)
        conn.execute("DELETE FROM indexed_documents")
        conn.commit()
        conn.close()

    def test_01_list_empty_library(self):
        """1. GET /api/files/list returns empty list and 0 total when no documents are indexed."""
        res = self.client.get("/api/files/list")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("documents", data)
        self.assertIn("total", data)
        self.assertEqual(data["documents"], [])
        self.assertEqual(data["total"], 0)

    def test_02_index_and_display_correct_count(self):
        """2. Display correct document count after indexing multiple documents."""
        # Index document 1
        res1 = self.client.post(
            "/api/files/index",
            data={"file": (io.BytesIO(b"Notes about machine learning algorithms."), "ml_notes.txt")},
            content_type="multipart/form-data"
        )
        self.assertEqual(res1.status_code, 201)

        # Index document 2
        res2 = self.client.post(
            "/api/files/index",
            data={"file": (io.BytesIO(b"# Developer Guide\nGuide for system integration."), "developer_guide.md")},
            content_type="multipart/form-data"
        )
        self.assertEqual(res2.status_code, 201)

        # Verify list endpoint
        res = self.client.get("/api/files/list")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["documents"]), 2)

    def test_03_display_correct_filenames_and_metadata(self):
        """3. Verify correct filenames, IDs, and indexed_at timestamps."""
        self.client.post(
            "/api/files/index",
            data={"file": (io.BytesIO(b"Project sprint planning details."), "sprint_plan.txt")},
            content_type="multipart/form-data"
        )
        res = self.client.get("/api/files/list")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["total"], 1)

        doc = data["documents"][0]
        self.assertEqual(doc["filename"], "sprint_plan.txt")
        self.assertIn("id", doc)
        self.assertIsInstance(doc["id"], int)
        self.assertIn("indexed_at", doc)
        self.assertTrue(len(doc["indexed_at"]) > 0)

    def test_04_refresh_library_consistency(self):
        """4. Refreshing the library returns consistent, stable results."""
        self.client.post(
            "/api/files/index",
            data={"file": (io.BytesIO(b"Document content for refresh test."), "refresh_test.txt")},
            content_type="multipart/form-data"
        )
        # Fetch multiple times
        res1 = self.client.get("/api/files/list")
        res2 = self.client.get("/api/files/list")
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res1.get_json(), res2.get_json())

    def test_05_reject_deletion_without_confirmation(self):
        """5. Reject index deletion without explicit confirmation (HTTP 400)."""
        idx_res = self.client.post(
            "/api/files/index",
            data={"file": (io.BytesIO(b"Important research findings."), "research.txt")},
            content_type="multipart/form-data"
        )
        doc_id = idx_res.get_json()["id"]

        # 1. No confirmation parameter
        del_res1 = self.client.delete(f"/api/files/index/{doc_id}")
        self.assertEqual(del_res1.status_code, 400)
        self.assertIn("Confirmation is required", del_res1.get_json().get("error", ""))

        # 2. confirm=false parameter
        del_res2 = self.client.delete(f"/api/files/index/{doc_id}?confirm=false")
        self.assertEqual(del_res2.status_code, 400)
        self.assertIn("Confirmation is required", del_res2.get_json().get("error", ""))

        # Verify document still exists in library
        list_res = self.client.get("/api/files/list")
        self.assertEqual(list_res.get_json()["total"], 1)

    def test_06_remove_indexed_record_with_confirmation(self):
        """6. Remove an indexed record with confirmation (HTTP 200)."""
        idx_res = self.client.post(
            "/api/files/index",
            data={"file": (io.BytesIO(b"Temporary notes to be removed."), "temp_note.txt")},
            content_type="multipart/form-data"
        )
        doc_id = idx_res.get_json()["id"]

        # Confirm removal via query parameter
        del_res = self.client.delete(f"/api/files/index/{doc_id}?confirm=true")
        self.assertEqual(del_res.status_code, 200)
        resp = del_res.get_json()
        self.assertEqual(resp.get("status"), "success")
        self.assertEqual(resp.get("id"), doc_id)
        self.assertIn("temp_note.txt", resp.get("message", ""))

        # Verify total is now 0
        list_res = self.client.get("/api/files/list")
        self.assertEqual(list_res.get_json()["total"], 0)

    def test_07_original_file_still_exists_on_disk(self):
        """7. Verify that removing a document from SQLite index NEVER deletes the original file on disk."""
        # Create a real file on disk
        original_filepath = os.path.join(self.temp_dir.name, "user_local_source.txt")
        file_text = "This is a precious user document that must NEVER be deleted from the disk."
        with open(original_filepath, "w", encoding="utf-8") as f:
            f.write(file_text)

        self.assertTrue(os.path.exists(original_filepath), "Original file must exist before indexing")

        # Index the file content
        with open(original_filepath, "rb") as f:
            idx_res = self.client.post(
                "/api/files/index",
                data={"file": (f, "user_local_source.txt")},
                content_type="multipart/form-data"
            )
        doc_id = idx_res.get_json()["id"]

        # Remove from index with confirmation
        del_res = self.client.delete(f"/api/files/index/{doc_id}?confirm=true")
        self.assertEqual(del_res.status_code, 200)

        # CRITICAL ASSERTION: The original physical file on disk must still exist unaltered!
        self.assertTrue(
            os.path.exists(original_filepath),
            "CRITICAL: The original physical file must still exist after removing its SQLite search index!"
        )
        with open(original_filepath, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), file_text, "Original physical file content must remain completely unmodified")

    def test_08_removed_document_no_longer_appears_in_search(self):
        """8. Verify the removed document no longer appears in search results."""
        idx_res = self.client.post(
            "/api/files/index",
            data={"file": (io.BytesIO(b"SecretKeywordXYZ unique content inside document."), "doc_to_remove.txt")},
            content_type="multipart/form-data"
        )
        doc_id = idx_res.get_json()["id"]

        # Verify it appears in search before deletion
        s_before = self.client.get("/api/files/search?q=SecretKeywordXYZ")
        self.assertEqual(s_before.status_code, 200)
        self.assertEqual(len(s_before.get_json()["results"]), 1)

        # Remove document
        self.client.delete(f"/api/files/index/{doc_id}?confirm=true")

        # Verify it NO LONGER appears in search
        s_after = self.client.get("/api/files/search?q=SecretKeywordXYZ")
        self.assertEqual(s_after.status_code, 200)
        self.assertEqual(s_after.get_json()["results"], [])

    def test_09_other_indexed_documents_remain(self):
        """9. Verify removing one document leaves other indexed documents completely intact."""
        # Index document A
        res_a = self.client.post(
            "/api/files/index",
            data={"file": (io.BytesIO(b"Alpha document with unique marker AlphaBeta."), "doc_a.txt")},
            content_type="multipart/form-data"
        )
        id_a = res_a.get_json()["id"]

        # Index document B
        res_b = self.client.post(
            "/api/files/index",
            data={"file": (io.BytesIO(b"Beta document with unique marker GammaDelta."), "doc_b.txt")},
            content_type="multipart/form-data"
        )
        id_b = res_b.get_json()["id"]

        # Delete document A only
        del_a = self.client.delete(f"/api/files/index/{id_a}?confirm=true")
        self.assertEqual(del_a.status_code, 200)

        # Verify Document B still exists in library
        list_res = self.client.get("/api/files/list")
        docs = list_res.get_json()["documents"]
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["id"], id_b)
        self.assertEqual(docs[0]["filename"], "doc_b.txt")

        # Verify Document B is still searchable
        search_res = self.client.get("/api/files/search?q=GammaDelta")
        self.assertEqual(search_res.status_code, 200)
        self.assertEqual(len(search_res.get_json()["results"]), 1)
        self.assertEqual(search_res.get_json()["results"][0]["filename"], "doc_b.txt")

    def test_10_json_confirmation_and_invalid_id_handling(self):
        """10. Support JSON confirmation body and reject invalid or nonexistent IDs."""
        idx_res = self.client.post(
            "/api/files/index",
            data={"file": (io.BytesIO(b"Test content for JSON body confirmation."), "json_confirm.txt")},
            content_type="multipart/form-data"
        )
        doc_id = idx_res.get_json()["id"]

        # Delete with JSON body: {"confirm": true}
        del_res = self.client.delete(
            f"/api/files/index/{doc_id}",
            json={"confirm": True}
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.get_json().get("status"), "success")

        # Nonexistent document ID
        del_nonexistent = self.client.delete("/api/files/index/99999?confirm=true")
        self.assertEqual(del_nonexistent.status_code, 404)
        self.assertIn("not found", del_nonexistent.get_json().get("error", "").lower())

        # Invalid string ID
        del_invalid = self.client.delete("/api/files/index/invalid_abc?confirm=true")
        self.assertEqual(del_invalid.status_code, 400)
        self.assertIn("valid integer", del_invalid.get_json().get("error", "").lower())


if __name__ == "__main__":
    unittest.main()
