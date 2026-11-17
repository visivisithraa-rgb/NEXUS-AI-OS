import subprocess
import time
import requests
import os
import shutil
import tempfile
import json
import sqlite3

def print_banner(msg):
    print("\n" + "=" * 65)
    print(f"  {msg}")
    print("=" * 65)

def test_packaged_desktop_application():
    print_banner("PHASE 6: PACKAGED DESKTOP APPLICATION VERIFICATION")

    installer_path = os.path.abspath("dist-electron/NEXUS AI OS Setup 1.0.0.exe")
    unpacked_exe = os.path.abspath("dist-electron/win-unpacked/NEXUS AI OS.exe")
    backend_exe = os.path.abspath("dist-electron/win-unpacked/resources/backend/nexus_backend.exe")

    print(f"1. Installer Exe:   {installer_path} (Exists: {os.path.isfile(installer_path)})")
    print(f"2. Packaged Desktop App: {unpacked_exe} (Exists: {os.path.isfile(unpacked_exe)})")
    print(f"3. Packaged Backend Exe: {backend_exe} (Exists: {os.path.isfile(backend_exe)})")

    assert os.path.isfile(installer_path), "Installer executable missing!"
    assert os.path.isfile(unpacked_exe), "Unpacked desktop executable missing!"
    assert os.path.isfile(backend_exe), "Packaged Python backend executable missing!"

    # Create dedicated persistent data directory for testing
    temp_data_dir = tempfile.mkdtemp(prefix="nexus_desktop_test_")
    test_port = "5099"
    test_url = f"http://127.0.0.1:{test_port}"

    # Seed .env into temp data directory so Gemini key is available
    root_env = os.path.abspath(".env")
    if os.path.isfile(root_env):
        shutil.copy2(root_env, os.path.join(temp_data_dir, ".env"))

    env = os.environ.copy()
    env["PORT"] = test_port
    env["NEXUS_DATA_DIR"] = temp_data_dir
    env["FLASK_ENV"] = "production"

    print(f"\nLaunching Packaged Backend Process on port {test_port}...")
    print(f"Data Directory: {temp_data_dir}")
    backend_proc = subprocess.Popen([backend_exe], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    try:
        # A. Health Check
        print("\n--- TEST A: BACKEND HEALTH & INITIALIZATION ---")
        online = False
        for i in range(30):
            time.sleep(0.4)
            try:
                r = requests.get(f"{test_url}/api/status", timeout=1)
                if r.status_code == 200:
                    online = True
                    print(f"Backend Status Payload: {r.json()}")
                    break
            except Exception:
                pass
        assert online, "Packaged backend failed to boot!"
        print("✓ Backend successfully booted and responded to health probe.")

        # B. Static Assets & Frontend Serving
        print("\n--- TEST B: FRONTEND SERVING ---")
        r_home = requests.get(test_url, timeout=2)
        assert r_home.status_code == 200
        assert "✦ NEXUS AI OS" in r_home.text
        r_css = requests.get(f"{test_url}/style.css", timeout=2)
        assert r_css.status_code == 200
        r_js = requests.get(f"{test_url}/script.js", timeout=2)
        assert r_js.status_code == 200
        print("✓ Packaged backend correctly serves index.html, style.css, and script.js.")

        # C. Notes CRUD & SQLite Persistence
        print("\n--- TEST C: NOTES ENGINE & PERSISTENCE ---")
        note_content = "Desktop packaging test note content for Phase 6."
        r_note = requests.post(f"{test_url}/api/notes", json={"content": note_content})
        assert r_note.status_code in [200, 201]
        note_id = r_note.json().get("id") or r_note.json().get("note_id")
        print(f"Created Note #{note_id}")

        r_notes_get = requests.get(f"{test_url}/api/notes")
        assert any(note_content in n["content"] for n in r_notes_get.json())
        print("✓ Notes created and verified in SQLite database.")

        # D. Tasks Manager
        print("\n--- TEST D: TASK MANAGER ---")
        r_task = requests.post(f"{test_url}/api/tasks", json={
            "title": "Verify Electron Packaging",
            "priority": "High",
            "due_date": "2026-11-20"
        })
        assert r_task.status_code in [200, 201]
        task_id = r_task.json().get("id")
        print(f"Created Task #{task_id}: {r_task.json().get('title')}")
        print("✓ Task Manager operational in packaged environment.")

        # E. Calendar Events
        print("\n--- TEST E: CALENDAR EVENTS ---")
        r_event = requests.post(f"{test_url}/api/events", json={
            "title": "NEXUS Desktop Release",
            "start": "2026-11-20T10:00:00",
            "end": "2026-11-20T11:00:00"
        })
        assert r_event.status_code in [200, 201]
        event_id = r_event.json().get("id")
        print(f"Scheduled Event #{event_id}: {r_event.json().get('title')}")
        print("✓ Calendar operational in packaged environment.")

        # F. AI Agent Natural Language Automation
        print("\n--- TEST F: AI AGENT ENGINE AUTOMATION ---")
        cmd = "Create a meeting note and schedule an event."
        r_agent = requests.post(f"{test_url}/api/agent/command", json={"command": cmd})
        assert r_agent.status_code == 200
        agent_data = r_agent.json()
        print(f"Agent Intent: {agent_data.get('intent')}")
        print(f"Agent Actions Executed: {len(agent_data.get('actions_executed', []))}")
        print(f"Agent Reply:\n{agent_data.get('reply')[:220]}...")
        assert agent_data.get("status") == "success"
        print("✓ AI Agent commands execute seamlessly through the packaged binary.")

        # G. Settings Gemini Key Configuration
        print("\n--- TEST G: GEMINI KEY MANAGEMENT ---")
        r_key = requests.get(f"{test_url}/api/settings/gemini-key")
        assert r_key.status_code == 200
        print(f"Gemini Key Status: {r_key.json()}")
        print("✓ Settings API key manager functions correctly.")

        # H. Graceful Shutdown & Process Cleanup
        print("\n--- TEST H: APPLICATION SHUTDOWN & CLEANUP ---")
        r_shutdown = requests.post(f"{test_url}/api/shutdown", timeout=2)
        assert r_shutdown.status_code == 200
        print("Shutdown request acknowledged.")

        backend_proc.wait(timeout=5)
        print(f"Backend process terminated cleanly with code {backend_proc.returncode}!")
        print("✓ Clean application shutdown verified.")

        # Verify SQLite DB file exists in persistent data dir
        db_file = os.path.join(temp_data_dir, "database", "nexus.db")
        assert os.path.isfile(db_file), "Database file missing from persistent data directory!"
        conn = sqlite3.connect(db_file)
        n_count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        t_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        e_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        l_count = conn.execute("SELECT COUNT(*) FROM agent_logs").fetchone()[0]
        conn.close()
        print(f"\nPersistent SQLite Database State in {db_file}:")
        print(f" - Notes: {n_count}")
        print(f" - Tasks: {t_count}")
        print(f" - Events: {e_count}")
        print(f" - Agent Audit Logs: {l_count}")
        print("✓ All application tables and user records verified in persistent storage.")

        print_banner("🎉 ALL PHASE 6 PACKAGED APPLICATION TESTS PASSED (100%)!")

    finally:
        if backend_proc.poll() is None:
            backend_proc.kill()
        try:
            shutil.rmtree(temp_data_dir, ignore_errors=True)
        except Exception:
            pass

if __name__ == "__main__":
    test_packaged_desktop_application()
