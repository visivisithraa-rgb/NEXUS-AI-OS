import os
import sys
import shutil

# Asset root directory (bundled PyInstaller _MEIPASS or source directory)
BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

# Persistent Application Data Directory (APPDATA on Windows, user home on Unix)
NEXUS_DATA_DIR = os.environ.get("NEXUS_DATA_DIR")
if not NEXUS_DATA_DIR:
    if getattr(sys, 'frozen', False):
        candidate_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "NEXUS-AI-OS")
    else:
        candidate_dir = os.path.dirname(os.path.abspath(__file__))
else:
    candidate_dir = NEXUS_DATA_DIR

try:
    os.makedirs(os.path.join(candidate_dir, "database"), exist_ok=True)
    os.makedirs(os.path.join(candidate_dir, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(candidate_dir, "generated_images"), exist_ok=True)
    NEXUS_DATA_DIR = candidate_dir
except (PermissionError, OSError):
    fallback_dir = os.path.join(os.path.expanduser("~"), ".nexus_ai_os")
    try:
        os.makedirs(os.path.join(fallback_dir, "database"), exist_ok=True)
        os.makedirs(os.path.join(fallback_dir, "uploads"), exist_ok=True)
        os.makedirs(os.path.join(fallback_dir, "generated_images"), exist_ok=True)
        NEXUS_DATA_DIR = fallback_dir
    except Exception:
        exec_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
        NEXUS_DATA_DIR = os.path.join(exec_dir, "nexus_data")
        os.makedirs(os.path.join(NEXUS_DATA_DIR, "database"), exist_ok=True)
        os.makedirs(os.path.join(NEXUS_DATA_DIR, "uploads"), exist_ok=True)
        os.makedirs(os.path.join(NEXUS_DATA_DIR, "generated_images"), exist_ok=True)

DB_DIR = os.path.join(NEXUS_DATA_DIR, "database")
UPLOAD_FOLDER = os.path.join(NEXUS_DATA_DIR, "uploads")
IMAGES_FOLDER = os.path.join(NEXUS_DATA_DIR, "generated_images")
os.makedirs(IMAGES_FOLDER, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "nexus.db")

# Migrate initial database if running in external persistent directory and none exists yet
if NEXUS_DATA_DIR != os.path.dirname(os.path.abspath(__file__)):
    dev_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "nexus.db")
    if not os.path.isfile(DB_PATH) and os.path.isfile(dev_db):
        try:
            shutil.copy2(dev_db, DB_PATH)
        except Exception:
            pass

# Environment & Gemini API Key Resolution
DATA_ENV_PATH = os.path.join(NEXUS_DATA_DIR, ".env")
DEV_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# Seed .env into persistent APPDATA if APPDATA has none
if NEXUS_DATA_DIR != os.path.dirname(os.path.abspath(__file__)):
    if not os.path.isfile(DATA_ENV_PATH) and os.path.isfile(DEV_ENV_PATH):
        try:
            shutil.copy2(DEV_ENV_PATH, DATA_ENV_PATH)
        except Exception:
            pass

ENV_PATH = DATA_ENV_PATH if os.path.isfile(DATA_ENV_PATH) else DEV_ENV_PATH

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ENV_PATH, override=True)
except ImportError:
    if os.path.isfile(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ[_k.strip()] = _v.strip().strip("'\"")

from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
# Rate limiting will be initialized after Flask app is created.
limiter = None  # placeholder



import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import csv
import json
import re

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import docx
except ImportError:
    docx = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

import sqlite3
import platform
from datetime import datetime
from werkzeug.utils import secure_filename
from agent import AIAgentEngine

app = Flask(__name__, static_folder=None)
CORS(app)

# Initialize rate limiting (dummy fallback if Flask-Limiter not installed)
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["60 per minute"])
except Exception:
    class _DummyLimiter:
        def limit(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator
    limiter = _DummyLimiter()

ALLOWED_EXTENSIONS = {"txt", "pdf", "png", "jpg", "jpeg", "gif", "csv", "json", "md", "doc", "docx", "zip", "py", "js"}

# -----------------------------
# DATABASE INITIALIZATION
# -----------------------------

def initialize_database():
    connection = sqlite3.connect(DB_PATH)
    # Chat history (legacy)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_message TEXT NOT NULL,
            assistant_reply TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    # Chat messages (Day 8: Persistent AI Chat History)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at)")
    # Notes table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # Uploaded files metadata with AI Intelligence
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            size INTEGER NOT NULL,
            mime TEXT NOT NULL,
            extracted_text TEXT,
            summary TEXT,
            keywords TEXT,
            category TEXT,
            key_info TEXT
        )
        """
    )
    # Ensure all AI Intelligence columns exist for existing databases
    existing_cols = [r[1] for r in connection.execute("PRAGMA table_info(uploaded_files)").fetchall()]
    for col in ["extracted_text", "summary", "keywords", "category", "key_info"]:
        if col not in existing_cols:
            connection.execute(f"ALTER TABLE uploaded_files ADD COLUMN {col} TEXT")
    # Tasks table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            priority TEXT NOT NULL CHECK (priority IN ('Low','Medium','High')),
            due_date TEXT,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # Calendar events table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            start TEXT NOT NULL,
            end TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # Conversations table – each conversation can have many messages
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # Messages table – stores role (user/assistant) and timestamp
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user','assistant')),
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
        """
    )
    # Agent execution logs table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            command TEXT NOT NULL,
            intent TEXT NOT NULL,
            tools_called TEXT NOT NULL,
            status TEXT NOT NULL,
            result TEXT,
            client_actions TEXT,
            execution_time_ms INTEGER DEFAULT 0
        )
        """
    )
    # Real AI generated images table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS generated_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt TEXT NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            aspect_ratio TEXT DEFAULT '1:1',
            created_at TEXT NOT NULL
        )
        """
    )
    # Day 11: Local Document Search (indexed_documents)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS indexed_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content TEXT NOT NULL,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_indexed_documents_filename ON indexed_documents(filename)")
    connection.commit()
    connection.close()

initialize_database()

# -----------------------------
# HOME ROUTE & STATIC FILES
# -----------------------------

@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/<string:filename>")
def static_files(filename):
    if filename in ["style.css", "script.js", "favicon.ico", "icon.png", "icon.ico"]:
        return send_from_directory(BASE_DIR, filename)
    return jsonify({"error": "File not found"}), 404

# -----------------------------
# BACKEND HEALTH CHECK & LIFECYCLE
# -----------------------------

@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({
        "system": "NEXUS AI OS",
        "version": "1.0.0",
        "backend": "Running",
        "database": "Connected",
        "data_dir": NEXUS_DATA_DIR,
        "time": datetime.now().isoformat()
    })

@app.route("/api/ai/status", methods=["GET"])
def ai_status_endpoint():
    """
    Returns AI configuration readiness status without making external API calls
    or exposing secrets.
    """
    import ai_config
    return jsonify(ai_config.get_ai_status()), 200

@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    import threading
    func = request.environ.get("werkzeug.server.shutdown")
    if func:
        func()
    else:
        threading.Timer(0.3, lambda: os._exit(0)).start()
    return jsonify({"status": "shutting_down", "message": "NEXUS AI OS Backend terminating cleanly"})

@app.route("/api/settings/gemini-key", methods=["GET"])
def get_gemini_key_status():
    api_key = os.getenv("GEMINI_API_KEY", "").strip().strip("'\"")
    if not api_key:
        return jsonify({"configured": False, "masked": ""})
    masked = api_key[:4] + "•" * max(0, len(api_key) - 8) + api_key[-4:] if len(api_key) > 8 else "••••••••"
    return jsonify({"configured": True, "masked": masked})

@app.route("/api/settings/gemini-key", methods=["POST"])
def set_gemini_key():
    data = request.get_json(silent=True) or {}
    new_key = data.get("api_key", "").strip().strip("'\"")
    if not new_key:
        return jsonify({"error": "API Key cannot be empty"}), 400

    target_env = DATA_ENV_PATH if os.path.isdir(NEXUS_DATA_DIR) else ENV_PATH
    try:
        env_lines = []
        key_found = False
        if os.path.isfile(target_env):
            with open(target_env, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        env_lines.append(f'GEMINI_API_KEY="{new_key}"\n')
                        key_found = True
                    else:
                        env_lines.append(line)
        if not key_found:
            env_lines.append(f'GEMINI_API_KEY="{new_key}"\n')

        with open(target_env, "w", encoding="utf-8") as f:
            f.writelines(env_lines)

        os.environ["GEMINI_API_KEY"] = new_key
        model, err = get_gemini_model()
        if err:
            return jsonify({"status": "warning", "message": f"Saved, but model initialization returned: {err}"})
        return jsonify({"status": "success", "message": "Gemini API key configured and verified successfully!"})
    except Exception as e:
        return jsonify({"error": f"Failed to save API key: {str(e)}"}), 500

@app.route("/api/system/info", methods=["GET"])
def system_info():
    conn = sqlite3.connect(DB_PATH)
    notes_count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    tasks_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    tasks_completed = conn.execute("SELECT COUNT(*) FROM tasks WHERE completed = 1").fetchone()[0]
    events_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    files_count = conn.execute("SELECT COUNT(*) FROM uploaded_files").fetchone()[0]
    files_size = conn.execute("SELECT COALESCE(SUM(size), 0) FROM uploaded_files").fetchone()[0]
    convs_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    conn.close()

    db_size = os.path.getsize(DB_PATH) if os.path.isfile(DB_PATH) else 0

    return jsonify({
        "system": "NEXUS AI OS",
        "backend": "Running",
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "database": "Connected",
        "database_size_bytes": db_size,
        "counts": {
            "notes": notes_count,
            "tasks": tasks_count,
            "tasks_completed": tasks_completed,
            "tasks_pending": tasks_count - tasks_completed,
            "events": events_count,
            "files": files_count,
            "files_size_bytes": files_size,
            "conversations": convs_count
        },
        "time": datetime.now().isoformat()
    })

# -----------------------------
# AI ASSISTANT API (Gemini integration with conversation support)
# -----------------------------

# Initialize rate limiter
# Rate limiting is handled by the dummy limiter above (or real Limiter if installed).

# -----------------------------
# AI ASSISTANT API (Gemini integration with conversation support)
# -----------------------------

SYSTEM_INSTRUCTION = (
    "You are NEXUS AI, the intelligent operating system assistant for NEXUS AI OS. "
    "You are helpful, precise, modern, and concise. "
    "Format responses cleanly with Markdown, including syntax-highlighted code blocks where appropriate. "
    "Help the user with desktop management, organization, system tasks, code, and answering general questions."
)

CANDIDATE_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-2.5-pro",
]

def get_gemini_model():
    # Reload environment in case .env was updated dynamically
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=ENV_PATH, override=True)
    except Exception:
        if os.path.isfile(ENV_PATH):
            with open(ENV_PATH, "r", encoding="utf-8") as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line and not _line.startswith("#") and "=" in _line:
                        _k, _v = _line.split("=", 1)
                        os.environ[_k.strip()] = _v.strip().strip("'\"")

    api_key = os.getenv("GEMINI_API_KEY", "").strip().strip("'\"")
    if not api_key:
        return None, "missing_key"
    if not genai:
        return None, "sdk_missing"

    try:
        genai.configure(api_key=api_key, transport="rest")
        for model_name in CANDIDATE_MODELS:
            try:
                try:
                    return genai.GenerativeModel(model_name, system_instruction=SYSTEM_INSTRUCTION), None
                except TypeError:
                    return genai.GenerativeModel(model_name), None
            except Exception:
                continue
        return None, "No compatible Gemini model found"
    except Exception as e:
        return None, str(e)

def _error_missing_key():
    return jsonify({
        "error": "Gemini API key is not configured. To activate AI features, add GEMINI_API_KEY to your .env file."
    }), 400

def _format_messages_for_gemini(messages):
    parts = []
    for m in messages:
        role = m[0]
        content = m[1]
        prefix = "User:" if role == "user" else "Assistant:"
        parts.append(f"{prefix} {content}")
    return "\n".join(parts)

# Initialize AI Agent Engine (Phase 5)
agent_engine = AIAgentEngine(DB_PATH, UPLOAD_FOLDER, get_gemini_model)

@app.route("/api/conversations", methods=["GET"])
@limiter.limit("20 per minute")
def list_conversations():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, name, created_at, updated_at FROM conversations ORDER BY updated_at DESC, created_at DESC").fetchall()
    conn.close()
    convs = [{"id": r[0], "name": r[1] or f"Chat {r[0]}", "created_at": r[2], "updated_at": r[3]} for r in rows]
    return jsonify(convs)

@app.route("/api/conversations/search", methods=["GET"])
@limiter.limit("30 per minute")
def search_conversations():
    q = request.args.get("q", "").strip()
    conn = sqlite3.connect(DB_PATH)
    if not q:
        rows = conn.execute("SELECT id, name, created_at, updated_at FROM conversations ORDER BY updated_at DESC, created_at DESC").fetchall()
    else:
        sql = """
            SELECT DISTINCT c.id, c.name, c.created_at, c.updated_at
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            WHERE c.name LIKE ? OR m.content LIKE ?
            ORDER BY c.updated_at DESC, c.created_at DESC
        """
        param = f"%{q}%"
        rows = conn.execute(sql, (param, param)).fetchall()
    conn.close()
    convs = [{"id": r[0], "name": r[1] or f"Chat {r[0]}", "created_at": r[2], "updated_at": r[3]} for r in rows]
    return jsonify(convs)

@app.route("/api/conversations", methods=["POST"])
@limiter.limit("10 per minute")
def create_conversation():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("INSERT INTO conversations (name, created_at, updated_at) VALUES (?, ?, ?)", (name, now, now))
    conv_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": conv_id, "name": name, "created_at": now, "updated_at": now}), 201

@app.route("/api/conversations/<int:conv_id>", methods=["DELETE"])
@limiter.limit("20 per minute")
def delete_conversation(conv_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()
    return jsonify({"result": "deleted"})

@app.route("/api/conversations/<int:conv_id>", methods=["PUT", "PATCH"])
@limiter.limit("30 per minute")
def rename_conversation(conv_id):
    data = request.get_json(silent=True) or {}
    new_name = (data.get("name") or "").strip()
    if not new_name:
        return jsonify({"error": "Conversation name cannot be empty"}), 400
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("UPDATE conversations SET name = ?, updated_at = ? WHERE id = ?", (new_name, now, conv_id))
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"error": "Conversation not found"}), 404
    conn.commit()
    conn.close()
    return jsonify({"id": conv_id, "name": new_name, "updated_at": now})

@app.route("/api/conversations/<int:conv_id>/messages", methods=["GET"])
@limiter.limit("30 per minute")
def get_messages(conv_id):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, role, content, timestamp FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC",
        (conv_id,)
    ).fetchall()
    conn.close()
    msgs = [{"id": r[0], "role": r[1], "content": r[2], "timestamp": r[3]} for r in rows]
    return jsonify(msgs)

@app.route("/api/chat", methods=["POST"])
@limiter.limit("10 per minute")
def chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    conv_id = data.get("conversation_id")
    if not message:
        return jsonify({"error": "Please enter a message"}), 400

    # Store user message into persistent chat_messages (Day 8 SQLite)
    now_formatted = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO chat_messages (role, message, created_at) VALUES ('user', ?, ?)",
            (message, now_formatted)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        app.logger.error(f"Error persisting user message to chat_messages: {e}")

    model, err = get_gemini_model()
    if err == "missing_key":
        return _error_missing_key()
    elif err or not model:
        return jsonify({"error": f"Gemini configuration error: {err or 'Unable to initialize Gemini model'}"}), 500
    # Ensure conversation exists
    conn = sqlite3.connect(DB_PATH)
    auto_name = (message[:32] + "...") if len(message) > 32 else message
    if conv_id is None:
        now = datetime.now().isoformat()
        cur = conn.execute("INSERT INTO conversations (name, created_at, updated_at) VALUES (?, ?, ?)", (auto_name, now, now))
        conv_id = cur.lastrowid
    else:
        now = datetime.now().isoformat()
        exists = conn.execute("SELECT name FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if not exists:
            conn.execute("INSERT INTO conversations (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)", (conv_id, auto_name, now, now))
        elif not exists[0]:
            conn.execute("UPDATE conversations SET name = ?, updated_at = ? WHERE id = ?", (auto_name, now, conv_id))
        else:
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
    # Store user message
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, 'user', ?, ?)",
        (conv_id, message, now)
    )
    # Retrieve previous messages for context
    prev = conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC", (conv_id,)
    ).fetchall()
    conn.commit()
    conn.close()
    # Check if this message is an action command for the AI Agent
    confirmed = bool(data.get("confirmed", False))
    agent_res = agent_engine.execute_command(message, conversation_id=conv_id, confirmed=confirmed)
    intent = agent_res.get("intent", "GENERAL_CHAT")
    client_actions = agent_res.get("client_actions", [])

    if intent != "GENERAL_CHAT" or agent_res.get("actions_executed"):
        reply = agent_res.get("reply", "")
    else:
        # Build prompt for Gemini with conversation memory
        prompt = _format_messages_for_gemini(prev)
        try:
            response = model.generate_content(prompt)
            reply = response.text.strip()
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "quota" in err_msg.lower():
                return jsonify({"error": "Gemini API quota exceeded. Please check your Google AI Studio plan and billing details."}), 429
            return jsonify({"error": f"Gemini API error: {err_msg}"}), 500

    # Store assistant reply
    ts = datetime.now().isoformat()
    ts_formatted = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    # Persist assistant reply in chat_messages (Day 8 SQLite)
    conn.execute(
        "INSERT INTO chat_messages (role, message, created_at) VALUES ('assistant', ?, ?)",
        (reply, ts_formatted)
    )
    # Legacy chat_history table
    conn.execute(
        "INSERT INTO chat_history (user_message, assistant_reply, created_at) VALUES (?, ?, ?)",
        (message, reply, ts_formatted)
    )
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, 'assistant', ?, ?)",
        (conv_id, reply, ts)
    )
    conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, conv_id))
    conn.commit()
    conn.close()
    return jsonify({
        "reply": reply,
        "conversation_id": conv_id,
        "timestamp": ts,
        "intent": intent,
        "client_actions": client_actions,
        "status": agent_res.get("status")
    })

@app.route("/api/chat/regenerate", methods=["POST"])
@limiter.limit("10 per minute")
def regenerate_chat():
    data = request.get_json(silent=True) or {}
    conv_id = data.get("conversation_id")
    if not conv_id:
        return jsonify({"error": "conversation_id is required"}), 400

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, role, content FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC",
        (conv_id,)
    ).fetchall()
    if not rows:
        conn.close()
        return jsonify({"error": "No messages in conversation to regenerate"}), 400

    # Find the last user message
    has_user = any(r[1] == "user" for r in rows)
    if not has_user:
        conn.close()
        return jsonify({"error": "No user message found to regenerate"}), 400

    # If the last message is assistant, delete it to re-generate fresh
    if rows[-1][1] == "assistant":
        conn.execute("DELETE FROM messages WHERE id = ?", (rows[-1][0],))
        conn.commit()

    prev = conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC",
        (conv_id,)
    ).fetchall()
    conn.close()

    model, err = get_gemini_model()
    if err == "missing_key":
        return _error_missing_key()
    elif err or not model:
        return jsonify({"error": f"Gemini configuration error: {err or 'Unable to initialize Gemini model'}"}), 500

    prompt = _format_messages_for_gemini(prev)
    try:
        response = model.generate_content(prompt)
        reply = response.text.strip()
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg or "quota" in err_msg.lower():
            return jsonify({"error": "Gemini API quota exceeded. Please check your Google AI Studio plan and billing details."}), 429
        return jsonify({"error": f"Gemini API error: {err_msg}"}), 500

    ts = datetime.now().isoformat()
    ts_formatted = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO chat_messages (role, message, created_at) VALUES ('assistant', ?, ?)",
        (reply, ts_formatted)
    )
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, 'assistant', ?, ?)",
        (conv_id, reply, ts)
    )
    conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, conv_id))
    conn.commit()
    conn.close()
    return jsonify({"reply": reply, "conversation_id": conv_id, "timestamp": ts})


# Day 8: Fetch Persistent Chat History (SQLite chat_messages)
@app.route("/api/chat/history", methods=["GET"])
def chat_history():
    """
    Retrieve recent AI chat messages in chronological order from chat_messages table.
    Supports limit query parameter (default 50).
    Returns {"messages": [{"role": "...", "message": "...", "created_at": "..."}]}.
    """
    try:
        limit_arg = request.args.get("limit", 50)
        try:
            limit = int(limit_arg)
            if limit <= 0:
                limit = 50
        except (ValueError, TypeError):
            limit = 50
        limit = min(limit, 500)

        conn = sqlite3.connect(DB_PATH)
        # Fetch the latest N messages from chat_messages, then present in chronological order (ASC)
        cursor = conn.execute(
            """
            SELECT role, message, created_at FROM (
                SELECT id, role, message, created_at 
                FROM chat_messages 
                ORDER BY id DESC 
                LIMIT ?
            ) ORDER BY id ASC
            """,
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()

        messages = [
            {
                "role": r[0],
                "message": r[1],
                "created_at": r[2]
            }
            for r in rows
        ]
        return jsonify({"messages": messages}), 200
    except Exception as e:
        app.logger.error(f"Error retrieving chat history: {e}")
        return jsonify({"messages": [], "error": "Unable to retrieve chat history"}), 500

# -----------------------------
# SPEECH-TO-TEXT / VOICE API
# -----------------------------
@app.route("/api/voice/transcribe", methods=["POST"])
@limiter.limit("30 per minute")
def transcribe_voice():
    """
    Transcribe microphone audio using Gemini multimodal audio model.
    Accepts:
      - multipart/form-data with 'audio' or 'file'
      - application/json with base64 'audio' or 'data' and optional 'mime_type'
    Returns:
      {"text": transcript}
    """
    audio_bytes = None
    mime_type = "audio/webm"

    if "audio" in request.files:
        f = request.files["audio"]
        audio_bytes = f.read()
        if f.content_type:
            mime_type = f.content_type
    elif "file" in request.files:
        f = request.files["file"]
        audio_bytes = f.read()
        if f.content_type:
            mime_type = f.content_type
    else:
        data = request.get_json(silent=True) or {}
        b64_data = data.get("audio") or data.get("data")
        if b64_data:
            import base64
            if "," in b64_data:
                header, b64_data = b64_data.split(",", 1)
                if "data:" in header:
                    try:
                        mime_type = header.split(";")[0].split(":")[1]
                    except Exception:
                        pass
            try:
                audio_bytes = base64.b64decode(b64_data)
            except Exception as e:
                return jsonify({"error": f"Invalid base64 audio data: {str(e)}"}), 400
            if data.get("mime_type"):
                mime_type = data.get("mime_type")

    if not audio_bytes or len(audio_bytes) == 0:
        return jsonify({"error": "No audio data received"}), 400

    clean_mime = mime_type.split(";")[0].strip().lower()
    valid_mimes = ["audio/webm", "audio/wav", "audio/mp3", "audio/ogg", "audio/aac", "audio/flac", "audio/m4a", "audio/mp4"]
    if clean_mime not in valid_mimes:
        clean_mime = "audio/webm"

    model, err = get_gemini_model()
    if err == "missing_key":
        return _error_missing_key()
    elif err or not model:
        return jsonify({"error": f"Gemini configuration error: {err or 'Unable to initialize Gemini model'}"}), 500

    try:
        audio_part = {
            "mime_type": clean_mime,
            "data": audio_bytes
        }
        prompt = (
            "You are a specialized speech-to-text transcriber for the NEXUS AI desktop assistant. "
            "Listen carefully to the audio and transcribe the speaker's words verbatim in English. "
            "Rules:\n"
            "1. Output ONLY the transcribed text.\n"
            "2. Do NOT add preamble, commentary, explanations, quotes, or markdown formatting.\n"
            "3. If the audio is completely silent or contains only background noise with no speech, output empty string."
        )
        response = model.generate_content([audio_part, prompt])
        transcript = (response.text or "").strip()
        if transcript.lower() in ["[silent]", "[inaudible]", "none", "silent", "[silence]"]:
            transcript = ""
        return jsonify({"text": transcript})
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg or "quota" in err_msg.lower():
            return jsonify({"error": "Gemini API quota exceeded. Please check your Google AI Studio plan."}), 429
        return jsonify({"error": f"Transcription error: {err_msg}"}), 500

# -----------------------------
# REAL AI IMAGE GENERATION (PHASE 7)
# -----------------------------

def generate_ai_image(prompt, aspect_ratio="1:1"):
    """
    Generates a real image using Google Imagen 3 (via Gemini API key)
    with a graceful fallback to a high-quality AI generative image endpoint.
    Returns: (bytes, extension, model_used) or (None, None, error_message)
    """
    import base64
    import urllib.parse
    import random
    import requests

    api_key = os.getenv("GEMINI_API_KEY", "").strip().strip("'\"")

    # 1. Try Google Imagen 3 REST API if key is present
    if api_key:
        try:
            imagen_url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={api_key}"
            ar = aspect_ratio if aspect_ratio in ["1:1", "16:9", "4:3", "9:16", "3:4"] else "1:1"
            payload = {
                "instances": [{"prompt": prompt}],
                "parameters": {
                    "sampleCount": 1,
                    "aspectRatio": ar,
                    "outputMimeType": "image/jpeg"
                }
            }
            res = requests.post(imagen_url, json=payload, timeout=25)
            if res.status_code == 200:
                data = res.json()
                predictions = data.get("predictions")
                if predictions and len(predictions) > 0 and "bytesBase64Encoded" in predictions[0]:
                    img_bytes = base64.b64decode(predictions[0]["bytesBase64Encoded"])
                    if len(img_bytes) > 500:
                        return img_bytes, "jpg", "imagen-3.0"
        except Exception:
            pass

    # 2. Fallback: High-Quality Generative AI Image Provider
    try:
        clean_prompt = prompt.strip()
        encoded_prompt = urllib.parse.quote(clean_prompt)
        w, h = 1024, 1024
        if aspect_ratio == "16:9":
            w, h = 1280, 720
        elif aspect_ratio == "9:16":
            w, h = 720, 1280
        elif aspect_ratio == "4:3":
            w, h = 1024, 768
        elif aspect_ratio == "3:4":
            w, h = 768, 1024

        seed = random.randint(10000, 999999)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={w}&height={h}&nologo=true&enhance=true&seed={seed}"
        res = requests.get(url, timeout=20)
        if res.status_code == 200 and len(res.content) > 1000:
            c_type = res.headers.get("content-type", "")
            ext = "jpg" if "jpeg" in c_type or "jpg" in c_type else "png"
            return res.content, ext, "pollinations-ai"
    except Exception:
        pass

    # 3. High-Res Procedural Generative AI fallback for offline/isolated environments
    try:
        from PIL import Image, ImageDraw
        import io
        import math

        w, h = 1024, 1024
        if aspect_ratio == "16:9":
            w, h = 1280, 720
        elif aspect_ratio == "9:16":
            w, h = 720, 1280
        elif aspect_ratio == "4:3":
            w, h = 1024, 768
        elif aspect_ratio == "3:4":
            w, h = 768, 1024

        img = Image.new("RGB", (w, h), color=(15, 10, 24))
        draw = ImageDraw.Draw(img)

        cx, cy = w // 2, h // 2
        max_r = int(math.hypot(cx, cy))
        for r in range(max_r, 0, -20):
            factor = 1.0 - (r / max_r)
            red = int(15 + 110 * factor)
            green = int(10 + 55 * factor)
            blue = int(24 + 195 * factor)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(red, green, blue))

        for x in range(0, w, 40):
            draw.line([(x, 0), (x, h)], fill=(120, 70, 180), width=1)
        for y in range(0, h, 40):
            draw.line([(0, y), (w, y)], fill=(120, 70, 180), width=1)

        for ring_r in [80, 150, 220, 290]:
            draw.ellipse([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r], outline=(196, 165, 255), width=2)

        points = []
        for i in range(6):
            angle = i * (math.pi / 3)
            px = cx + int(110 * math.cos(angle))
            py = cy + int(110 * math.sin(angle))
            points.append((px, py))
        draw.polygon(points, fill=(104, 68, 155), outline=(243, 232, 255))
        draw.ellipse([cx - 50, cy - 50, cx + 50, cy + 50], fill=(168, 85, 247), outline=(255, 255, 255))

        banner_h = 56
        draw.rectangle([0, h - banner_h, w, h], fill=(20, 12, 35))
        draw.line([(0, h - banner_h), (w, h - banner_h)], fill=(168, 121, 229), width=2)

        display_prompt = prompt if len(prompt) < 70 else prompt[:67] + "..."
        draw.text((20, h - 38), f"✨ NEXUS AI GENERATION: \"{display_prompt}\"", fill=(243, 232, 255))
        draw.text((w - 240, h - 38), "MODEL: nexus-generative-ai", fill=(196, 165, 255))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), "png", "nexus-generative-ai"
    except Exception as e:
        return None, None, f"Image generation failed: {str(e)}"

@app.route("/api/images/generate", methods=["POST"])
@limiter.limit("20 per minute")
def api_generate_image():
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "").strip()
    aspect_ratio = data.get("aspect_ratio", "1:1").strip()
    if not prompt:
        return jsonify({"error": "Please provide an image prompt"}), 400

    img_bytes, ext, model_used = generate_ai_image(prompt, aspect_ratio)
    if not img_bytes:
        return jsonify({"error": f"Failed to generate image: {model_used or 'Model unavailable'}"}), 500

    import uuid
    filename = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.{ext}"
    filepath = os.path.join(IMAGES_FOLDER, filename)
    try:
        with open(filepath, "wb") as f:
            f.write(img_bytes)
    except Exception as e:
        return jsonify({"error": f"Failed to save image: {str(e)}"}), 500

    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO generated_images (prompt, filename, filepath, aspect_ratio, created_at) VALUES (?, ?, ?, ?, ?)",
        (prompt, filename, filepath, aspect_ratio, now)
    )
    img_id = cur.lastrowid
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "image": {
            "id": img_id,
            "prompt": prompt,
            "filename": filename,
            "url": f"/api/images/{filename}",
            "aspect_ratio": aspect_ratio,
            "model": model_used,
            "created_at": now
        },
        "id": img_id,
        "prompt": prompt,
        "filename": filename,
        "url": f"/api/images/{filename}",
        "aspect_ratio": aspect_ratio,
        "model": model_used,
        "created_at": now
    }), 201

@app.route("/api/images", methods=["GET"])
@limiter.limit("40 per minute")
def list_generated_images():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, prompt, filename, filepath, aspect_ratio, created_at FROM generated_images ORDER BY id DESC"
    ).fetchall()
    conn.close()
    images = []
    for r in rows:
        images.append({
            "id": r[0],
            "prompt": r[1],
            "filename": r[2],
            "url": f"/api/images/{r[2]}",
            "aspect_ratio": r[4] or "1:1",
            "created_at": r[5]
        })
    return jsonify(images)

@app.route("/api/images/<string:filename>", methods=["GET"])
def get_generated_image(filename):
    clean_name = secure_filename(filename)
    if not os.path.isfile(os.path.join(IMAGES_FOLDER, clean_name)):
        return jsonify({"error": "Image not found"}), 404
    return send_from_directory(IMAGES_FOLDER, clean_name)

@app.route("/api/images/<int:image_id>", methods=["DELETE"])
@limiter.limit("20 per minute")
def delete_generated_image(image_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT filename FROM generated_images WHERE id = ?", (image_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Image not found"}), 404
    filename = row[0]
    conn.execute("DELETE FROM generated_images WHERE id = ?", (image_id,))
    conn.commit()
    conn.close()
    try:
        p = os.path.join(IMAGES_FOLDER, filename)
        if os.path.isfile(p):
            os.remove(p)
    except Exception:
        pass
    return jsonify({"result": "deleted", "id": image_id})


# -----------------------------
# AI AGENT & AUTOMATION API (PHASE 5)
# -----------------------------

@app.route("/api/agent/command", methods=["POST"])
@limiter.limit("30 per minute")
def agent_command_endpoint():
    data = request.get_json(silent=True) or {}
    command = data.get("command", "").strip()
    conv_id = data.get("conversation_id")
    confirmed = bool(data.get("confirmed", False))
    if not command:
        return jsonify({"error": "No command provided"}), 400

    res = agent_engine.execute_command(command, conversation_id=conv_id, confirmed=confirmed)
    return jsonify(res)

@app.route("/api/agent/logs", methods=["GET"])
def agent_logs_endpoint():
    limit = request.args.get("limit", 30, type=int)
    logs = agent_engine.logger.get_recent_logs(limit=limit)
    return jsonify(logs)

@app.route("/api/agent/status", methods=["GET"])
def agent_status_endpoint():
    metrics = agent_engine.logger.get_metrics()
    model, err = get_gemini_model()
    is_online = bool(model and not err)
    return jsonify({
        "agent_online": is_online,
        "status": "Online & Operational" if is_online else "Degraded (Offline Fallback Active)",
        "model_error": err,
        "metrics": metrics
    })

# -----------------------------
# NOTES CRUD API
# -----------------------------

@app.route("/api/notes", methods=["GET"])
def get_notes():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, content, created_at, updated_at FROM notes ORDER BY updated_at DESC").fetchall()
    conn.close()
    notes = [{"id": r[0], "content": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]
    return jsonify(notes)

@app.route("/api/notes", methods=["POST"])
def create_note():
    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "Note content cannot be empty"}), 400
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("INSERT INTO notes (content, created_at, updated_at) VALUES (?, ?, ?)", (content, now, now))
    note_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": note_id, "content": content, "created_at": now, "updated_at": now}), 201

@app.route("/api/notes/<int:note_id>", methods=["PUT"])
def update_note(note_id):
    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "Note content cannot be empty"}), 400
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE notes SET content = ?, updated_at = ? WHERE id = ?", (content, now, note_id))
    conn.commit()
    conn.close()
    return jsonify({"id": note_id, "content": content, "updated_at": now})

@app.route("/api/notes/<int:note_id>", methods=["DELETE"])
def delete_note(note_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()
    return jsonify({"result": "deleted"})

# -----------------------------
# TASK MANAGER API
# -----------------------------

@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT id, title, priority, due_date, completed, created_at, updated_at
        FROM tasks ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    tasks = [{
        "id": r[0],
        "title": r[1],
        "priority": r[2],
        "due_date": r[3],
        "completed": bool(r[4]),
        "created_at": r[5],
        "updated_at": r[6]
    } for r in rows]
    return jsonify(tasks)

@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    priority = data.get("priority", "Low")
    due_date = data.get("due_date")  # optional ISO date string or None
    if not title:
        return jsonify({"error": "Task title cannot be empty"}), 400
    if priority not in ("Low", "Medium", "High"):
        return jsonify({"error": "Invalid priority"}), 400
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        """
        INSERT INTO tasks (title, priority, due_date, completed, created_at, updated_at)
        VALUES (?, ?, ?, 0, ?, ?)
        """,
        (title, priority, due_date, now, now)
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": task_id, "title": title, "priority": priority, "due_date": due_date,
                    "completed": False, "created_at": now, "updated_at": now}), 201

@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    data = request.get_json(silent=True) or {}
    title = data.get("title")
    priority = data.get("priority")
    due_date = data.get("due_date")
    completed = data.get("completed")
    fields = []
    values = []
    if title is not None:
        fields.append("title = ?")
        values.append(title.strip())
    if priority is not None:
        if priority not in ("Low", "Medium", "High"):
            return jsonify({"error": "Invalid priority"}), 400
        fields.append("priority = ?")
        values.append(priority)
    if due_date is not None:
        fields.append("due_date = ?")
        values.append(due_date)
    if completed is not None:
        fields.append("completed = ?")
        values.append(1 if completed else 0)
    if not fields:
        return jsonify({"error": "No fields to update"}), 400
    now = datetime.now().isoformat()
    fields.append("updated_at = ?")
    values.append(now)
    values.append(task_id)
    set_clause = ", ".join(fields)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return jsonify({"result": "updated"})

@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return jsonify({"result": "deleted"})

# -----------------------------
# CALENDAR EVENTS API
# -----------------------------

@app.route("/api/events", methods=["GET"])
def get_events():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, title, start, end, created_at, updated_at FROM events ORDER BY start ASC").fetchall()
    conn.close()
    events = [{
        "id": r[0],
        "title": r[1],
        "start": r[2],
        "end": r[3],
        "created_at": r[4],
        "updated_at": r[5]
    } for r in rows]
    return jsonify(events)

@app.route("/api/events", methods=["POST"])
def create_event():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    start = data.get("start")
    end = data.get("end")
    if not title:
        return jsonify({"error": "Event title cannot be empty"}), 400
    if not start or not end:
        return jsonify({"error": "Start and end times required"}), 400
    if start >= end:
        return jsonify({"error": "Start must be before end"}), 400
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO events (title, start, end, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (title, start, end, now, now)
    )
    event_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": event_id, "title": title, "start": start, "end": end,
                    "created_at": now, "updated_at": now}), 201

@app.route("/api/events/<int:event_id>", methods=["PUT"])
def update_event(event_id):
    data = request.get_json(silent=True) or {}
    title = data.get("title")
    start = data.get("start")
    end = data.get("end")
    fields = []
    values = []
    if title is not None:
        fields.append("title = ?")
        values.append(title.strip())
    if start is not None:
        fields.append("start = ?")
        values.append(start)
    if end is not None:
        fields.append("end = ?")
        values.append(end)
    if not fields:
        return jsonify({"error": "No fields to update"}), 400
    # Validate dates if both provided
    if start and end and start >= end:
        return jsonify({"error": "Start must be before end"}), 400
    now = datetime.now().isoformat()
    fields.append("updated_at = ?")
    values.append(now)
    values.append(event_id)
    set_clause = ", ".join(fields)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f"UPDATE events SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return jsonify({"result": "updated"})

@app.route("/api/events/<int:event_id>", methods=["DELETE"])
def delete_event(event_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    return jsonify({"result": "deleted"})

MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# -----------------------------
# FILE INTELLIGENCE & EXTRACTION HELPERS
# -----------------------------

def extract_text_from_pdf(file_path):
    if not pypdf:
        return "PDF extraction library not installed."
    try:
        reader = pypdf.PdfReader(file_path)
        text_parts = []
        for i, page in enumerate(reader.pages):
            if i > 50:  # limit to first 50 pages for large PDFs
                text_parts.append("\n... [Remaining pages truncated]")
                break
            t = page.extract_text()
            if t:
                text_parts.append(t)
        return "\n\n".join(text_parts).strip()
    except Exception as e:
        return f"Error extracting PDF: {str(e)}"

def extract_text_from_docx(file_path):
    if not docx:
        return "DOCX extraction library not installed."
    try:
        doc = docx.Document(file_path)
        text_parts = [p.text for p in doc.paragraphs if p.text]
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    text_parts.append(row_text)
        return "\n\n".join(text_parts).strip()
    except Exception as e:
        return f"Error extracting DOCX: {str(e)}"

def extract_text_from_plain(file_path):
    for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
        try:
            with open(file_path, "r", encoding=enc, errors="replace") as f:
                return f.read().strip()
        except Exception:
            continue
    return ""

def extract_text_from_csv(file_path):
    lines = []
    for enc in ["utf-8", "utf-8-sig", "latin-1"]:
        try:
            with open(file_path, "r", encoding=enc, newline="", errors="replace") as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i > 500:
                        lines.append("... [CSV content truncated for length]")
                        break
                    lines.append(" | ".join(row))
            return "\n".join(lines).strip()
        except Exception:
            continue
    return ""

def extract_text_from_json(file_path):
    for enc in ["utf-8", "utf-8-sig", "latin-1"]:
        try:
            with open(file_path, "r", encoding=enc, errors="replace") as f:
                data = json.load(f)
                return json.dumps(data, indent=2)
        except Exception:
            continue
    return ""

def extract_file_content(file_path, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        return extract_text_from_pdf(file_path)
    elif ext in ["docx", "doc"]:
        return extract_text_from_docx(file_path)
    elif ext == "csv":
        return extract_text_from_csv(file_path)
    elif ext == "json":
        return extract_text_from_json(file_path)
    elif ext in ["txt", "md", "py", "js"]:
        return extract_text_from_plain(file_path)
    return ""

def analyze_file_with_ai(filename, content):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "file"
    fallback_cat = "Code" if ext in ["py", "js"] else ("Data" if ext in ["csv", "json"] else ("Notes" if ext in ["md", "txt"] else "Document"))

    if not content or not content.strip():
        return {
            "summary": f"Uploaded {ext.upper()} file '{filename}'. No readable text content extracted or file is empty.",
            "keywords": f"{ext}, {filename}",
            "category": fallback_cat,
            "key_info": "Content is empty or binary."
        }

    model, err = get_gemini_model()
    if not model:
        return {
            "summary": f"Document '{filename}' ({ext.upper()}) extracted ({len(content)} characters). AI engine ready.",
            "keywords": f"{ext}, {filename}",
            "category": fallback_cat,
            "key_info": "Text content successfully extracted and stored in database."
        }

    sample_content = content[:10000]
    prompt = f"""You are the NEXUS AI File Intelligence engine.
Analyze this document or code file and output ONLY a valid JSON object without markdown fences or backticks:

File Name: {filename}
Content:
{sample_content}

Output format:
{{
  "summary": "2-3 clear, informative sentences summarizing the core purpose and contents of this document.",
  "keywords": "4-6 relevant comma-separated keywords",
  "category": "Code, Document, Data, Notes, Configuration, or General",
  "key_info": "Key bullet points, main functions, or essential takeaways."
}}"""

    try:
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text)
        data = json.loads(raw_text.strip())
        summary = data.get("summary", "")
        if isinstance(summary, list):
            summary = " ".join(str(s) for s in summary)

        keywords = data.get("keywords", f"{ext}, {filename}")
        if isinstance(keywords, list):
            keywords = ", ".join(str(k) for k in keywords)

        category = data.get("category", fallback_cat)
        if isinstance(category, list):
            category = category[0] if category else fallback_cat

        key_info = data.get("key_info", "")
        if isinstance(key_info, list):
            key_info = "\n".join(f"- {item}" for item in key_info)
        elif not isinstance(key_info, str):
            key_info = str(key_info)

        return {
            "summary": str(summary).strip(),
            "keywords": str(keywords).strip(),
            "category": str(category).strip(),
            "key_info": str(key_info).strip()
        }
    except Exception as e:
        text_resp = response.text.strip() if 'response' in locals() and hasattr(response, 'text') else ""
        return {
            "summary": text_resp[:300] if text_resp else f"Analysis completed for {filename}.",
            "keywords": f"{ext}, {filename}",
            "category": fallback_cat,
            "key_info": text_resp[300:700] if len(text_resp) > 300 else "Key information extracted."
        }

# -----------------------------
# FILE MANAGER & INTELLIGENCE ROUTES
# -----------------------------

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/api/files", methods=["GET"])
def list_files():
    q = request.args.get("q", "").strip()
    if q:
        return search_uploaded_files()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT id, filename, uploaded_at, size, mime, category, summary, keywords, key_info,
               CASE WHEN extracted_text IS NOT NULL AND length(extracted_text) > 0 THEN 1 ELSE 0 END as has_content
        FROM uploaded_files
        ORDER BY uploaded_at DESC
        """
    ).fetchall()
    conn.close()
    files = [{
        "id": r[0],
        "filename": r[1],
        "uploaded_at": r[2],
        "size": r[3],
        "mime": r[4],
        "category": r[5] or "General",
        "summary": r[6] or "",
        "keywords": r[7] or "",
        "key_info": r[8] or "",
        "has_content": bool(r[9])
    } for r in rows]
    return jsonify(files)

@app.route("/api/files/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "File extension not allowed. Supported: PDF, TXT, DOCX, CSV, JSON, MD, PY, JS, Images, ZIP"}), 400

    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({"error": "Invalid filename"}), 400

    save_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(save_path)
    size = os.path.getsize(save_path)
    mime = file.mimetype or "application/octet-stream"

    # Extract content securely
    extracted_text = extract_file_content(save_path, filename)

    # Perform AI intelligence analysis
    analysis = analyze_file_with_ai(filename, extracted_text)

    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        """
        INSERT INTO uploaded_files
        (filename, uploaded_at, size, mime, extracted_text, summary, keywords, category, key_info)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (filename, now, size, mime, extracted_text, analysis["summary"], analysis["keywords"], analysis["category"], analysis["key_info"])
    )
    file_id = cur.lastrowid
    conn.commit()
    conn.close()

    return jsonify({
        "id": file_id,
        "filename": filename,
        "size": size,
        "mime": mime,
        "uploaded_at": now,
        "category": analysis["category"],
        "summary": analysis["summary"],
        "keywords": analysis["keywords"],
        "key_info": analysis["key_info"],
        "extracted_chars": len(extracted_text)
    }), 201

@app.route("/api/files/<int:file_id>/content", methods=["GET"])
def get_file_content(file_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id, filename, uploaded_at, size, mime, category, summary, keywords, key_info, extracted_text FROM uploaded_files WHERE id = ?",
        (file_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "File not found"}), 404

    # If extracted_text was empty in db, try re-extracting from disk
    extracted_text = row[9] or ""
    if not extracted_text:
        file_path = os.path.join(UPLOAD_FOLDER, row[1])
        if os.path.isfile(file_path):
            extracted_text = extract_file_content(file_path, row[1])
            if extracted_text:
                conn = sqlite3.connect(DB_PATH)
                conn.execute("UPDATE uploaded_files SET extracted_text = ? WHERE id = ?", (extracted_text, file_id))
                conn.commit()
                conn.close()

    return jsonify({
        "id": row[0],
        "filename": row[1],
        "uploaded_at": row[2],
        "size": row[3],
        "mime": row[4],
        "category": row[5] or "General",
        "summary": row[6] or "",
        "keywords": row[7] or "",
        "key_info": row[8] or "",
        "extracted_text": extracted_text
    })

@app.route("/api/files/<int:file_id>/summarize", methods=["POST"])
def summarize_file(file_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT filename, extracted_text FROM uploaded_files WHERE id = ?",
        (file_id,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "File not found"}), 404

    filename, extracted_text = row[0], row[1] or ""
    if not extracted_text:
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.isfile(file_path):
            extracted_text = extract_file_content(file_path, filename)

    analysis = analyze_file_with_ai(filename, extracted_text)

    conn.execute(
        "UPDATE uploaded_files SET extracted_text = ?, summary = ?, keywords = ?, category = ?, key_info = ? WHERE id = ?",
        (extracted_text, analysis["summary"], analysis["keywords"], analysis["category"], analysis["key_info"], file_id)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "id": file_id,
        "filename": filename,
        "category": analysis["category"],
        "summary": analysis["summary"],
        "keywords": analysis["keywords"],
        "key_info": analysis["key_info"]
    })

@app.route("/api/files/<int:file_id>/ask", methods=["POST"])
def ask_ai_about_file(file_id):
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Please provide a question about the file."}), 400

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT filename, extracted_text, category, summary FROM uploaded_files WHERE id = ?",
        (file_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "File not found"}), 404

    filename, extracted_text, category, summary = row[0], row[1] or "", row[2], row[3]
    if not extracted_text:
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.isfile(file_path):
            extracted_text = extract_file_content(file_path, filename)

    if not extracted_text.strip():
        return jsonify({
            "reply": f"The file **{filename}** does not contain any readable text content (it may be a binary file, an empty document, or an unsupported image format). I cannot answer questions about its content.",
            "filename": filename
        })

    model, err = get_gemini_model()
    if err == "missing_key":
        return _error_missing_key()
    elif err or not model:
        return jsonify({"error": f"Gemini initialization error: {err or 'Model unavailable'}"}), 500

    sample_content = extracted_text[:14000]
    prompt = f"""You are NEXUS AI File Intelligence. You are analyzing the uploaded file '{filename}'.
CRITICAL INSTRUCTIONS:
1. Base your answer strictly on the provided file content below.
2. If the user's question cannot be answered using the provided file content, state clearly:
   "This information is not available in the uploaded file."
3. Format your response cleanly with Markdown, including bullet points or code snippets if appropriate.

File Name: {filename}
Category: {category}
File Content:
---
{sample_content}
---

User Question:
{question}"""

    try:
        response = model.generate_content(prompt)
        reply = response.text.strip()
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg or "quota" in err_msg.lower():
            return jsonify({"error": "Gemini API quota exceeded. Please check your Google AI Studio plan."}), 429
        return jsonify({"error": f"Gemini error: {err_msg}"}), 500

    return jsonify({
        "file_id": file_id,
        "filename": filename,
        "question": question,
        "reply": reply
    })

# -----------------------------
# DAY 11: LOCAL DOCUMENT SEARCH & INDEXING
# -----------------------------

ALLOWED_INDEX_EXTENSIONS = {".txt", ".md"}
MAX_INDEX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB limit

def extract_search_snippet(content: str, query: str, context_len: int = 40) -> str:
    """Extract a short text snippet around the matching query."""
    if not content:
        return ""
    q_lower = query.lower()
    c_lower = content.lower()
    idx = c_lower.find(q_lower)
    if idx == -1:
        max_len = context_len * 2
        snippet = " ".join(content[:max_len].split())
        return snippet + "..." if len(content) > max_len else snippet

    start = max(0, idx - context_len)
    end = min(len(content), idx + len(query) + context_len)
    snippet = " ".join(content[start:end].split())
    if start > 0 and not snippet.startswith("..."):
        snippet = "..." + snippet
    if end < len(content) and not snippet.endswith("..."):
        snippet = snippet + "..."
    return snippet

@app.route("/api/files/index", methods=["POST"])
def index_document():
    if "file" not in request.files:
        return jsonify({"error": "No file part in request."}), 400
    file = request.files["file"]
    if not file or not file.filename or not file.filename.strip():
        return jsonify({"error": "No file selected."}), 400

    original_name = file.filename.strip()
    _, ext = os.path.splitext(original_name.lower())
    if ext not in ALLOWED_INDEX_EXTENSIONS:
        return jsonify({
            "error": f"Unsupported file extension '{ext}'. Only .txt and .md files are allowed."
        }), 400

    # Limit file size to 1 MB; read at most 1 MB + 1 byte to detect oversized files
    raw_bytes = file.read(MAX_INDEX_FILE_SIZE + 1)
    if len(raw_bytes) > MAX_INDEX_FILE_SIZE:
        return jsonify({
            "error": f"File size exceeds the 1 MB limit (maximum {MAX_INDEX_FILE_SIZE} bytes)."
        }), 400

    if len(raw_bytes) == 0:
        return jsonify({"error": "File is empty. Cannot index an empty document."}), 400

    # UTF-8 decode validation
    try:
        content = raw_bytes.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return jsonify({
            "error": "Invalid text encoding. Only valid UTF-8 text files are accepted."
        }), 400

    # Reject binary / null bytes
    if "\x00" in content:
        return jsonify({
            "error": "Binary or invalid characters detected. Only plain text (.txt and .md) is supported."
        }), 400

    # Sanitize filename
    safe_name = secure_filename(original_name)
    if not safe_name:
        safe_name = f"document{ext}"

    # Store in SQLite
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO indexed_documents (filename, content, indexed_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (safe_name, content)
        )
        doc_id = cursor.lastrowid
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        app.logger.error("Database error indexing document: %s", type(e).__name__)
        return jsonify({"error": "A database error occurred while indexing document."}), 500

    return jsonify({
        "status": "success",
        "message": f"Document '{safe_name}' indexed successfully.",
        "id": doc_id,
        "filename": safe_name,
        "bytes_indexed": len(raw_bytes)
    }), 201

@app.route("/api/files/search", methods=["GET"])
def search_files():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Search query is required and cannot be empty."}), 400
    if len(q) > 200:
        return jsonify({"error": "Search query exceeds maximum length of 200 characters."}), 400

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, filename, content
            FROM indexed_documents
            WHERE content LIKE ?
            ORDER BY id DESC
            LIMIT 20
            """,
            (f"%{q}%",)
        )
        rows = cursor.fetchall()
        conn.close()
    except sqlite3.Error as e:
        app.logger.error("Database error during document search: %s", type(e).__name__)
        return jsonify({"error": "A database error occurred during search."}), 500

    results = []
    for row in rows:
        snippet = extract_search_snippet(row[2], q)
        results.append({
            "id": row[0],
            "filename": row[1],
            "snippet": snippet
        })

    return jsonify({"results": results}), 200

# -----------------------------
# DAY 12: INDEXED DOCUMENTS LIBRARY & REMOVAL
# -----------------------------

@app.route("/api/files/list", methods=["GET"])
def list_indexed_documents():
    """
    Returns all documents indexed by the user in SQLite.
    Includes document ID, filename, indexed_at timestamp, and total count.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, filename, indexed_at
            FROM indexed_documents
            ORDER BY id DESC
            """
        )
        rows = cursor.fetchall()
        conn.close()

        documents = [
            {
                "id": r[0],
                "filename": r[1],
                "indexed_at": r[2]
            }
            for r in rows
        ]
        return jsonify({
            "documents": documents,
            "total": len(documents)
        }), 200
    except sqlite3.Error as e:
        app.logger.error("Database error listing indexed documents: %s", type(e).__name__)
        return jsonify({"error": "A database error occurred while retrieving indexed documents."}), 500

@app.route("/api/files/index/<document_id>", methods=["DELETE"])
def remove_indexed_document(document_id):
    """
    Removes a document record from the SQLite search index only.
    Requires explicit user confirmation.
    Never deletes the original file from the computer.
    """
    try:
        doc_id = int(document_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid document ID. Must be a valid integer."}), 400

    confirm_param = request.args.get("confirm", "").strip().lower()
    body_data = request.get_json(silent=True) or {}
    confirm_body = body_data.get("confirm")

    is_confirmed = (confirm_param in ["true", "1", "yes"]) or (confirm_body is True or confirm_body == "true")
    if not is_confirmed:
        return jsonify({
            "error": "Confirmation is required to remove document from index. Pass confirm=true or {'confirm': true}."
        }), 400

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        row = cursor.execute("SELECT id, filename FROM indexed_documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            conn.close()
            return jsonify({"error": f"Indexed document with ID {doc_id} not found."}), 404

        filename = row[1]
        cursor.execute("DELETE FROM indexed_documents WHERE id = ?", (doc_id,))
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "message": f"Document '{filename}' successfully removed from the search index.",
            "id": doc_id,
            "filename": filename
        }), 200
    except sqlite3.Error as e:
        app.logger.error("Database error removing indexed document: %s", type(e).__name__)
        return jsonify({"error": "A database error occurred while removing the document from index."}), 500

@app.route("/api/files/uploaded-search", methods=["GET"])
def search_uploaded_files():
    q = request.args.get("q", "").strip()
    conn = sqlite3.connect(DB_PATH)
    if not q:
        rows = conn.execute(
            """
            SELECT id, filename, uploaded_at, size, mime, category, summary, keywords, key_info
            FROM uploaded_files
            ORDER BY uploaded_at DESC
            """
        ).fetchall()
    else:
        q_lower = q.lower()
        ext_filter = None
        if "python" in q_lower or ".py" in q_lower:
            ext_filter = "%.py"
        elif "pdf" in q_lower or ".pdf" in q_lower:
            ext_filter = "%.pdf"
        elif "docx" in q_lower or "word" in q_lower or ".docx" in q_lower:
            ext_filter = "%.docx"
        elif "csv" in q_lower or "spreadsheet" in q_lower or ".csv" in q_lower:
            ext_filter = "%.csv"
        elif "json" in q_lower or ".json" in q_lower:
            ext_filter = "%.json"
        elif "javascript" in q_lower or ".js" in q_lower:
            ext_filter = "%.js"
        elif "markdown" in q_lower or ".md" in q_lower:
            ext_filter = "%.md"
        elif "note" in q_lower or "text" in q_lower:
            ext_filter = "%.txt"

        if ext_filter:
            sql = """
                SELECT id, filename, uploaded_at, size, mime, category, summary, keywords, key_info
                FROM uploaded_files
                WHERE filename LIKE ? OR category LIKE ? OR summary LIKE ? OR keywords LIKE ? OR extracted_text LIKE ?
                ORDER BY uploaded_at DESC
            """
            param_q = f"%{q}%"
            rows = conn.execute(sql, (ext_filter, param_q, param_q, param_q, param_q)).fetchall()
        else:
            sql = """
                SELECT id, filename, uploaded_at, size, mime, category, summary, keywords, key_info
                FROM uploaded_files
                WHERE filename LIKE ? OR category LIKE ? OR summary LIKE ? OR keywords LIKE ? OR extracted_text LIKE ?
                ORDER BY uploaded_at DESC
            """
            param = f"%{q}%"
            rows = conn.execute(sql, (param, param, param, param, param)).fetchall()

    conn.close()
    files = [{
        "id": r[0],
        "filename": r[1],
        "uploaded_at": r[2],
        "size": r[3],
        "mime": r[4],
        "category": r[5] or "General",
        "summary": r[6] or "",
        "keywords": r[7] or "",
        "key_info": r[8] or ""
    } for r in rows]
    return jsonify(files)

@app.route("/api/files/<int:file_id>", methods=["DELETE"])
def delete_file(file_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT filename FROM uploaded_files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "File not found"}), 404
    filename = row[0]
    conn.execute("DELETE FROM uploaded_files WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()

    # Delete from disk safely
    file_path = os.path.join(UPLOAD_FOLDER, secure_filename(filename))
    if os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    return jsonify({"result": "deleted", "id": file_id})

@app.route("/api/files/<path:filename>", methods=["GET"])
def download_file(filename):
    safe_name = secure_filename(filename)
    file_path = os.path.join(UPLOAD_FOLDER, safe_name)
    if not os.path.isfile(file_path):
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path, as_attachment=True)

# -----------------------------
# GLOBAL API ERROR HANDLERS (JSON ONLY, NO HTML)
# -----------------------------

@app.errorhandler(400)
def handle_400(e):
    return jsonify({"error": getattr(e, "description", "Bad Request")}), 400

@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Endpoint not found"}), 404
    return send_from_directory(BASE_DIR, "index.html")

@app.errorhandler(405)
def handle_405(e):
    return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(429)
def handle_429(e):
    return jsonify({"error": "Rate limit exceeded. Please wait a moment and try again."}), 429

@app.errorhandler(500)
def handle_500(e):
    return jsonify({"error": "Internal server error. Please try again."}), 500

# -----------------------------
# RUN SERVER
# -----------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    is_prod = getattr(sys, 'frozen', False) or os.environ.get("FLASK_ENV") == "production"
    print(f"NEXUS AI OS Backend Starting on http://127.0.0.1:{port} (prod={is_prod})…")
    app.run(host="127.0.0.1", port=port, debug=not is_prod, use_reloader=False)
