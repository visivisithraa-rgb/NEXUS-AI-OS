"""
NEXUS AI OS - Day 11 Automated Test Suite
Secure Local Document Search & SQLite Indexing

Tests:
1. Valid TXT file indexing.
2. Valid Markdown file indexing.
3. Search for an existing keyword.
4. Search for a missing keyword.
5. Empty search query (and excessively long query).
6. Unsupported file extension.
7. Oversized file (> 1 MB).
8. Invalid text encoding & binary rejection.
9. SQL injection-style search input.
10. Result limit (capped at 20).
"""

import io
import os
import sqlite3
import tempfile
import unittest

import app as nexus_app
from app import app, initialize_database


class TestLocalDocumentSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary directory for test database
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

    def test_01_valid_txt_indexing(self):
        """1. Valid TXT file indexing stores content and filename in SQLite."""
        txt_content = b"Python is a versatile programming language used for artificial intelligence."
        data = {
            "file": (io.BytesIO(txt_content), "python_notes.txt")
        }
        res = self.client.post("/api/files/index", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 201)
        resp = res.get_json()
        self.assertEqual(resp.get("status"), "success")
        self.assertEqual(resp.get("filename"), "python_notes.txt")
        self.assertIn("id", resp)

        # Verify record in SQLite database
        conn = sqlite3.connect(nexus_app.DB_PATH)
        row = conn.execute(
            "SELECT filename, content FROM indexed_documents WHERE id = ?",
            (resp["id"],)
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "python_notes.txt")
        self.assertEqual(row[1], txt_content.decode("utf-8"))

    def test_02_valid_markdown_indexing(self):
        """2. Valid Markdown (.md) file indexing."""
        md_content = b"# Architecture Overview\nThis document describes NEXUS AI OS desktop system design."
        data = {
            "file": (io.BytesIO(md_content), "architecture.md")
        }
        res = self.client.post("/api/files/index", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 201)
        resp = res.get_json()
        self.assertEqual(resp.get("status"), "success")
        self.assertEqual(resp.get("filename"), "architecture.md")

        # Verify in SQLite
        conn = sqlite3.connect(nexus_app.DB_PATH)
        row = conn.execute(
            "SELECT filename, content FROM indexed_documents WHERE id = ?",
            (resp["id"],)
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "architecture.md")
        self.assertIn("NEXUS AI OS", row[1])

    def test_03_search_existing_keyword(self):
        """3. Search for an existing keyword returns filename and snippet."""
        res = self.client.get("/api/files/search?q=programming")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("results", data)
        self.assertIsInstance(data["results"], list)
        self.assertGreaterEqual(len(data["results"]), 1)

        first = data["results"][0]
        self.assertIn("filename", first)
        self.assertIn("snippet", first)
        self.assertEqual(first["filename"], "python_notes.txt")
        self.assertIn("programming", first["snippet"].lower())

    def test_04_search_missing_keyword(self):
        """4. Search for a missing keyword returns empty results list."""
        res = self.client.get("/api/files/search?q=quantum_cryptography_nonexistent_xyz")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("results", data)
        self.assertEqual(data["results"], [])

    def test_05_empty_search_query(self):
        """5. Empty search query or query exceeding 200 characters is rejected."""
        # Empty query parameter
        res_empty = self.client.get("/api/files/search?q=")
        self.assertEqual(res_empty.status_code, 400)
        self.assertIn("error", res_empty.get_json())

        # Missing query parameter
        res_missing = self.client.get("/api/files/search")
        self.assertEqual(res_missing.status_code, 400)
        self.assertIn("error", res_missing.get_json())

        # Whitespace-only query
        res_spaces = self.client.get("/api/files/search?q=   ")
        self.assertEqual(res_spaces.status_code, 400)
        self.assertIn("error", res_spaces.get_json())

        # Excessively long query (> 200 characters)
        long_query = "a" * 250
        res_long = self.client.get(f"/api/files/search?q={long_query}")
        self.assertEqual(res_long.status_code, 400)
        self.assertIn("error", res_long.get_json())

    def test_06_unsupported_file_extension(self):
        """6. Unsupported file extensions (e.g. .pdf, .py, .exe, .csv) are rejected."""
        unsupported = [
            ("script.py", b"print('hello')"),
            ("document.pdf", b"%PDF-1.4 binary data"),
            ("malicious.exe", b"MZ binary payload"),
            ("data.csv", b"a,b,c\n1,2,3")
        ]
        for filename, content in unsupported:
            data = {"file": (io.BytesIO(content), filename)}
            res = self.client.post("/api/files/index", data=data, content_type="multipart/form-data")
            self.assertEqual(res.status_code, 400, f"Expected 400 for {filename}")
            self.assertIn("error", res.get_json())
            self.assertIn("Unsupported file extension", res.get_json()["error"])

    def test_07_oversized_file(self):
        """7. Oversized file (> 1 MB limit) is rejected."""
        # 1 MB + 100 bytes
        oversized_bytes = b"X" * (1024 * 1024 + 100)
        data = {"file": (io.BytesIO(oversized_bytes), "oversized.txt")}
        res = self.client.post("/api/files/index", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)
        resp = res.get_json()
        self.assertIn("error", resp)
        self.assertIn("1 MB", resp["error"])

    def test_08_invalid_text_encoding(self):
        """8. Invalid text encoding and binary characters are rejected."""
        # Non-UTF-8 bytes
        invalid_utf8 = b"\x80\xFF\xFE\xFD"
        data1 = {"file": (io.BytesIO(invalid_utf8), "bad_encoding.txt")}
        res1 = self.client.post("/api/files/index", data=data1, content_type="multipart/form-data")
        self.assertEqual(res1.status_code, 400)
        self.assertIn("encoding", res1.get_json().get("error", "").lower())

        # Binary content with null bytes
        binary_with_null = b"Hello\x00World\x00NullBytes"
        data2 = {"file": (io.BytesIO(binary_with_null), "binary.txt")}
        res2 = self.client.post("/api/files/index", data=data2, content_type="multipart/form-data")
        self.assertEqual(res2.status_code, 400)
        self.assertIn("binary", res2.get_json().get("error", "").lower())

    def test_09_sql_injection_search(self):
        """9. SQL injection-style search input is treated as literal search text."""
        injection_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE indexed_documents; --",
            "\" OR \"\"=\"",
            "admin'--"
        ]
        for payload in injection_payloads:
            res = self.client.get(f"/api/files/search?q={payload}")
            self.assertEqual(res.status_code, 200, f"Failed on payload: {payload}")
            data = res.get_json()
            self.assertIn("results", data)
            self.assertIsInstance(data["results"], list)

        # Verify table still exists and data intact
        conn = sqlite3.connect(nexus_app.DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM indexed_documents").fetchone()[0]
        conn.close()
        self.assertGreater(count, 0, "indexed_documents table should remain intact")

    def test_10_result_limit(self):
        """10. Search results are capped at a maximum limit of 20."""
        # Index 25 documents containing a unique limit benchmark token
        token = "limit_cap_benchmark_token"
        for i in range(25):
            content = f"Document entry number {i:02d} with unique marker {token} inside.".encode("utf-8")
            data = {"file": (io.BytesIO(content), f"benchmark_{i:02d}.txt")}
            res = self.client.post("/api/files/index", data=data, content_type="multipart/form-data")
            self.assertEqual(res.status_code, 201)

        res = self.client.get(f"/api/files/search?q={token}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 20, "Results must be capped at exactly 20")


if __name__ == "__main__":
    unittest.main()
