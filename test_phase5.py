import json
import sqlite3
import os
from app import app, DB_PATH

def print_separator(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

client = app.test_client()

def test_agent_status():
    print_separator("TEST 0: AGENT STATUS ENDPOINT")
    res = client.get("/api/agent/status")
    print(f"Status Code: {res.status_code}")
    data = res.get_json()
    print(f"Agent Online: {data.get('agent_online')}")
    print(f"Status: {data.get('status')}")
    print(f"Metrics: {json.dumps(data.get('metrics', {}), indent=2)}")
    assert res.status_code == 200
    assert "metrics" in data

def test_command_1_create_note():
    print_separator("TEST 1: 'Create a note about my AI project.'")
    cmd = "Create a note about my AI project."
    res = client.post("/api/agent/command", json={"command": cmd})
    print(f"Status Code: {res.status_code}")
    data = res.get_json()
    print(f"Intent: {data.get('intent')}")
    print(f"Actions Executed: {len(data.get('actions_executed', []))}")
    print(f"Reply:\n{data.get('reply')[:200]}...")
    
    assert res.status_code == 200
    assert data.get("status") == "success"
    assert data.get("intent") in ["CREATE", "CREATE_NOTE"]
    
    # Verify in SQLite database
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id, content FROM notes WHERE content LIKE '%AI project%' ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    print(f"DB Verification: Note #{row[0]} -> '{row[1]}'")
    assert row is not None

def test_command_2_create_task():
    print_separator("TEST 2: 'Add a high-priority task for tomorrow.'")
    cmd = "Add a high-priority task for tomorrow."
    res = client.post("/api/agent/command", json={"command": cmd})
    print(f"Status Code: {res.status_code}")
    data = res.get_json()
    print(f"Intent: {data.get('intent')}")
    print(f"Reply:\n{data.get('reply')[:200]}...")
    
    assert res.status_code == 200
    assert data.get("status") == "success"
    
    # Verify in SQLite database
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id, title, priority, due_date FROM tasks WHERE priority = 'High' ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    print(f"DB Verification: Task #{row[0]} -> '{row[1]}', Priority: {row[2]}, Due: {row[3]}")
    assert row is not None
    assert row[2] == "High"

def test_command_3_schedule_event():
    print_separator("TEST 3: 'Schedule an event tomorrow at 3 PM.'")
    cmd = "Schedule an event tomorrow at 3 PM."
    res = client.post("/api/agent/command", json={"command": cmd})
    print(f"Status Code: {res.status_code}")
    data = res.get_json()
    print(f"Intent: {data.get('intent')}")
    print(f"Reply:\n{data.get('reply')[:200]}...")
    
    assert res.status_code == 200
    assert data.get("status") == "success"
    
    # Verify in SQLite database
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id, title, start, end FROM events ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    print(f"DB Verification: Event #{row[0]} -> '{row[1]}', Start: {row[2]}, End: {row[3]}")
    assert row is not None

def test_command_4_summarize_pdf():
    print_separator("TEST 4: 'Find my latest PDF and summarize it.'")
    cmd = "Find my latest PDF and summarize it."
    res = client.post("/api/agent/command", json={"command": cmd})
    print(f"Status Code: {res.status_code}")
    data = res.get_json()
    print(f"Intent: {data.get('intent')}")
    print(f"Actions Executed: {len(data.get('actions_executed', []))}")
    print(f"Reply:\n{data.get('reply')[:250]}...")
    
    assert res.status_code == 200
    assert data.get("status") == "success"
    assert len(data.get("actions_executed", [])) >= 1

def test_command_5_show_pending_tasks():
    print_separator("TEST 5: 'Show my pending tasks.'")
    cmd = "Show my pending tasks."
    res = client.post("/api/agent/command", json={"command": cmd})
    print(f"Status Code: {res.status_code}")
    data = res.get_json()
    print(f"Intent: {data.get('intent')}")
    print(f"Reply:\n{data.get('reply')[:200]}...")
    
    assert res.status_code == 200
    assert data.get("status") == "success"

def test_command_6_multistep_workflow():
    print_separator("TEST 6: 'Create a meeting note and schedule an event.'")
    cmd = "Create a meeting note and schedule an event."
    res = client.post("/api/agent/command", json={"command": cmd})
    print(f"Status Code: {res.status_code}")
    data = res.get_json()
    print(f"Intent: {data.get('intent')}")
    print(f"Actions Executed: {len(data.get('actions_executed', []))}")
    for act in data.get("actions_executed", []):
        print(f"  Step {act['step']}: {act['tool']} -> {act.get('description')}")
    print(f"Client Actions: {data.get('client_actions')}")
    print(f"Reply:\n{data.get('reply')[:250]}...")
    
    assert res.status_code == 200
    assert data.get("status") == "success"
    assert len(data.get("actions_executed", [])) >= 2

def test_safety_and_permissions():
    print_separator("TEST 7: SAFETY & PERMISSION CONFIRMATION")
    # First create a task to delete
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("INSERT INTO tasks (title, priority, due_date, completed, created_at, updated_at) VALUES ('Task to be deleted safely', 'Low', '', 0, '2026-11-15', '2026-11-15')")
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    # Try deleting without confirmation
    cmd = f"delete task {task_id}"
    res = client.post("/api/agent/command", json={"command": cmd, "confirmed": False})
    data = res.get_json()
    print(f"Unconfirmed Delete Status: {data.get('status')}")
    print(f"Confirmation Prompt: {data.get('confirmation_prompt')}")
    assert data.get("status") == "confirmation_required"
    
    # Verify task still exists in DB
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    assert row is not None, "Task should NOT be deleted without confirmation!"
    print("Verified: Task still exists in database without confirmation.")
    
    # Now provide confirmed = True
    res_conf = client.post("/api/agent/command", json={"command": cmd, "confirmed": True})
    data_conf = res_conf.get_json()
    print(f"Confirmed Delete Status: {data_conf.get('status')}")
    assert data_conf.get("status") == "success"
    
    # Verify task is now deleted
    conn = sqlite3.connect(DB_PATH)
    row_del = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    assert row_del is None, "Task should be deleted after explicit confirmation!"
    print("Verified: Task successfully deleted after explicit confirmation.")

def test_agent_logs():
    print_separator("TEST 8: AGENT EXECUTION LOG AUDITING")
    res = client.get("/api/agent/logs?limit=10")
    print(f"Status Code: {res.status_code}")
    logs = res.get_json()
    print(f"Total Logs Returned: {len(logs)}")
    assert len(logs) > 0
    latest = logs[0]
    print(f"Latest Log -> Command: '{latest['command']}', Intent: {latest['intent']}, Status: {latest['status']}, Time: {latest['execution_time_ms']}ms")
    assert "tools_called" in latest
    assert "timestamp" in latest

def test_chat_integration():
    print_separator("TEST 9: CHAT INTEGRATION WITH AGENT TOOLS")
    res = client.post("/api/chat", json={"message": "Add a high-priority task for tomorrow."})
    print(f"Status Code: {res.status_code}")
    data = res.get_json()
    print(f"Chat Reply: {data.get('reply')[:150]}...")
    print(f"Intent: {data.get('intent')}")
    print(f"Client Actions: {data.get('client_actions')}")
    assert res.status_code == 200
    assert "reply" in data

if __name__ == "__main__":
    try:
        test_agent_status()
        test_command_1_create_note()
        test_command_2_create_task()
        test_command_3_schedule_event()
        test_command_4_summarize_pdf()
        test_command_5_show_pending_tasks()
        test_command_6_multistep_workflow()
        test_safety_and_permissions()
        test_agent_logs()
        test_chat_integration()
        print("\n" + "=" * 60)
        print("🎉 ALL PHASE 5 TESTS PASSED WITH 100% SUCCESS!")
        print("=" * 60)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ Test Failed: {e}")
        exit(1)
