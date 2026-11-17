import os
import sqlite3
import json
import re
import time
from datetime import datetime, timedelta

# ==============================================================================
# 1. PERMISSION MANAGER & SAFETY
# ==============================================================================

class PermissionManager:
    """Enforces safety rules and confirmation requirements for destructive actions."""
    DESTRUCTIVE_TOOLS = {"delete_note", "delete_task", "delete_event", "delete_file"}

    @classmethod
    def is_destructive(cls, tool_name: str) -> bool:
        return tool_name in cls.DESTRUCTIVE_TOOLS

    @classmethod
    def check_permission(cls, tool_name: str, params: dict, confirmed: bool) -> tuple[bool, str]:
        if cls.is_destructive(tool_name) and not confirmed:
            target_id = params.get("id") or params.get("note_id") or params.get("task_id") or params.get("event_id") or params.get("file_id")
            item_name = tool_name.replace("delete_", "")
            msg = f"⚠️ Confirmation Required: Are you sure you want to permanently delete {item_name} #{target_id}?"
            return False, msg
        return True, ""


# ==============================================================================
# 2. APPLICATION TOOLS REGISTRY
# ==============================================================================

class ApplicationTools:
    """Direct interface for the AI Agent to execute actions across NEXUS apps."""

    def __init__(self, db_path: str, upload_folder: str, get_gemini_model_fn):
        self.db_path = db_path
        self.upload_folder = upload_folder
        self.get_gemini_model = get_gemini_model_fn

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    # --- NOTES TOOLS ---

    def create_note(self, content: str) -> dict:
        if not content or not content.strip():
            return {"error": "Note content cannot be empty."}
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO notes (content, created_at, updated_at) VALUES (?, ?, ?)",
                (content.strip(), now, now)
            )
            note_id = cur.lastrowid
            conn.commit()
        return {
            "status": "success",
            "action": "create_note",
            "note_id": note_id,
            "preview": content[:80] + ("..." if len(content) > 80 else ""),
            "message": f"Created Note #{note_id}: \"{content[:50]}...\""
        }

    def search_notes(self, query: str = "") -> dict:
        with self._get_connection() as conn:
            if query:
                rows = conn.execute(
                    "SELECT id, content, created_at, updated_at FROM notes WHERE content LIKE ? ORDER BY updated_at DESC",
                    (f"%{query}%",)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, content, created_at, updated_at FROM notes ORDER BY updated_at DESC LIMIT 10"
                ).fetchall()
        notes = [{"id": r[0], "content": r[1], "created_at": r[2]} for r in rows]
        return {
            "status": "success",
            "action": "search_notes",
            "count": len(notes),
            "notes": notes,
            "message": f"Found {len(notes)} note(s)."
        }

    def edit_note(self, note_id: int, content: str) -> dict:
        if not content:
            return {"error": "Content cannot be empty."}
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE notes SET content = ?, updated_at = ? WHERE id = ?",
                (content.strip(), now, note_id)
            )
            if cur.rowcount == 0:
                return {"error": f"Note #{note_id} not found."}
            conn.commit()
        return {
            "status": "success",
            "action": "edit_note",
            "note_id": note_id,
            "message": f"Updated Note #{note_id}."
        }

    def delete_note(self, note_id: int, confirmed: bool = False) -> dict:
        allowed, msg = PermissionManager.check_permission("delete_note", {"note_id": note_id}, confirmed)
        if not allowed:
            return {"status": "confirmation_required", "tool": "delete_note", "note_id": note_id, "prompt": msg}
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            if cur.rowcount == 0:
                return {"error": f"Note #{note_id} not found."}
            conn.commit()
        return {
            "status": "success",
            "action": "delete_note",
            "note_id": note_id,
            "message": f"Deleted Note #{note_id}."
        }

    def summarize_note(self, note_id: int) -> dict:
        with self._get_connection() as conn:
            row = conn.execute("SELECT content FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not row:
            return {"error": f"Note #{note_id} not found."}
        content = row[0]
        model, _ = self.get_gemini_model()
        if model:
            try:
                res = model.generate_content(f"Summarize this note in 1-2 concise sentences:\n{content}")
                summary = res.text.strip()
            except Exception as e:
                summary = content[:150]
        else:
            summary = content[:150]
        return {
            "status": "success",
            "action": "summarize_note",
            "note_id": note_id,
            "summary": summary,
            "message": f"Summary of Note #{note_id}: {summary}"
        }

    # --- TASK MANAGER TOOLS ---

    def create_task(self, title: str, priority: str = "Medium", due_date: str = "") -> dict:
        if not title or not title.strip():
            return {"error": "Task title cannot be empty."}
        p_clean = priority.strip().capitalize() if priority else "Medium"
        if p_clean not in ["Low", "Medium", "High"]:
            p_clean = "Medium"

        # Parse relative date
        parsed_due = self._parse_date_string(due_date) if due_date else ""
        now = datetime.now().isoformat()

        with self._get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO tasks (title, priority, due_date, completed, created_at, updated_at) VALUES (?, ?, ?, 0, ?, ?)",
                (title.strip(), p_clean, parsed_due, now, now)
            )
            task_id = cur.lastrowid
            conn.commit()
        return {
            "status": "success",
            "action": "create_task",
            "task_id": task_id,
            "title": title.strip(),
            "priority": p_clean,
            "due_date": parsed_due,
            "message": f"Created Task #{task_id}: \"{title.strip()}\" [Priority: {p_clean}, Due: {parsed_due or 'No date'}]"
        }

    def list_tasks(self, status: str = "pending") -> dict:
        with self._get_connection() as conn:
            if status == "pending":
                rows = conn.execute(
                    "SELECT id, title, priority, due_date, completed FROM tasks WHERE completed = 0 ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, created_at DESC"
                ).fetchall()
            elif status == "completed":
                rows = conn.execute(
                    "SELECT id, title, priority, due_date, completed FROM tasks WHERE completed = 1 ORDER BY updated_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, title, priority, due_date, completed FROM tasks ORDER BY completed ASC, created_at DESC"
                ).fetchall()
        tasks = [{"id": r[0], "title": r[1], "priority": r[2], "due_date": r[3], "completed": bool(r[4])} for r in rows]
        return {
            "status": "success",
            "action": "list_tasks",
            "count": len(tasks),
            "status_filter": status,
            "tasks": tasks,
            "message": f"Found {len(tasks)} {status} task(s)."
        }

    def complete_task(self, task_id: int) -> dict:
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE tasks SET completed = 1, updated_at = ? WHERE id = ?",
                (now, task_id)
            )
            if cur.rowcount == 0:
                return {"error": f"Task #{task_id} not found."}
            conn.commit()
        return {
            "status": "success",
            "action": "complete_task",
            "task_id": task_id,
            "message": f"Marked Task #{task_id} as completed."
        }

    def delete_task(self, task_id: int, confirmed: bool = False) -> dict:
        allowed, msg = PermissionManager.check_permission("delete_task", {"task_id": task_id}, confirmed)
        if not allowed:
            return {"status": "confirmation_required", "tool": "delete_task", "task_id": task_id, "prompt": msg}
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            if cur.rowcount == 0:
                return {"error": f"Task #{task_id} not found."}
            conn.commit()
        return {
            "status": "success",
            "action": "delete_task",
            "task_id": task_id,
            "message": f"Deleted Task #{task_id}."
        }

    def update_task(self, task_id: int, title: str = None, priority: str = None, due_date: str = None, completed: int = None) -> dict:
        now = datetime.now().isoformat()
        updates = []
        params = []
        if title is not None and title.strip():
            updates.append("title = ?")
            params.append(title.strip())
        if priority is not None:
            p_clean = priority.strip().capitalize()
            if p_clean in ["Low", "Medium", "High"]:
                updates.append("priority = ?")
                params.append(p_clean)
        if due_date is not None:
            parsed_due = self._parse_date_string(due_date) if due_date else ""
            updates.append("due_date = ?")
            params.append(parsed_due)
        if completed is not None:
            updates.append("completed = ?")
            params.append(int(bool(completed)))
        if not updates:
            return {"error": "No updates specified."}
        updates.append("updated_at = ?")
        params.append(now)
        params.append(task_id)
        with self._get_connection() as conn:
            cur = conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", tuple(params))
            if cur.rowcount == 0:
                return {"error": f"Task #{task_id} not found."}
            conn.commit()
        return {
            "status": "success",
            "action": "update_task",
            "task_id": task_id,
            "message": f"Updated Task #{task_id}."
        }

    # --- CALENDAR TOOLS ---

    def create_event(self, title: str, start: str, end: str = "") -> dict:
        if not title or not title.strip():
            return {"error": "Event title cannot be empty."}
        parsed_start = self._parse_datetime_string(start, default_hour=15)
        parsed_end = self._parse_datetime_string(end, default_hour=16) if end else self._add_hours(parsed_start, 1)

        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO events (title, start, end, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (title.strip(), parsed_start, parsed_end, now, now)
            )
            event_id = cur.lastrowid
            conn.commit()
        return {
            "status": "success",
            "action": "create_event",
            "event_id": event_id,
            "title": title.strip(),
            "start": parsed_start,
            "end": parsed_end,
            "message": f"Scheduled Event #{event_id}: \"{title.strip()}\" from {parsed_start} to {parsed_end}."
        }

    def list_events(self, filter_type: str = "upcoming") -> dict:
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            if filter_type == "today":
                today_start = datetime.now().replace(hour=0, minute=0, second=0).isoformat()
                today_end = datetime.now().replace(hour=23, minute=59, second=59).isoformat()
                rows = conn.execute(
                    "SELECT id, title, start, end FROM events WHERE start BETWEEN ? AND ? ORDER BY start ASC",
                    (today_start, today_end)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, title, start, end FROM events WHERE start >= ? ORDER BY start ASC LIMIT 10",
                    (now,)
                ).fetchall()
                if not rows:  # Fallback to recent events if none in future
                    rows = conn.execute(
                        "SELECT id, title, start, end FROM events ORDER BY start DESC LIMIT 10"
                    ).fetchall()
        events = [{"id": r[0], "title": r[1], "start": r[2], "end": r[3]} for r in rows]
        return {
            "status": "success",
            "action": "list_events",
            "count": len(events),
            "events": events,
            "message": f"Found {len(events)} event(s)."
        }

    def delete_event(self, event_id: int, confirmed: bool = False) -> dict:
        allowed, msg = PermissionManager.check_permission("delete_event", {"event_id": event_id}, confirmed)
        if not allowed:
            return {"status": "confirmation_required", "tool": "delete_event", "event_id": event_id, "prompt": msg}
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
            if cur.rowcount == 0:
                return {"error": f"Event #{event_id} not found."}
            conn.commit()
        return {
            "status": "success",
            "action": "delete_event",
            "event_id": event_id,
            "message": f"Deleted Event #{event_id}."
        }

    def update_event(self, event_id: int, title: str = None, start: str = None, end: str = None) -> dict:
        now = datetime.now().isoformat()
        updates = []
        params = []
        if title is not None and title.strip():
            updates.append("title = ?")
            params.append(title.strip())
        if start is not None and start.strip():
            parsed_start = self._parse_datetime_string(start, default_hour=15)
            updates.append("start = ?")
            params.append(parsed_start)
        if end is not None and end.strip():
            parsed_end = self._parse_datetime_string(end, default_hour=16)
            updates.append("end = ?")
            params.append(parsed_end)
        if not updates:
            return {"error": "No updates specified."}
        updates.append("updated_at = ?")
        params.append(now)
        params.append(event_id)
        with self._get_connection() as conn:
            cur = conn.execute(f"UPDATE events SET {', '.join(updates)} WHERE id = ?", tuple(params))
            if cur.rowcount == 0:
                return {"error": f"Event #{event_id} not found."}
            conn.commit()
        return {
            "status": "success",
            "action": "update_event",
            "event_id": event_id,
            "message": f"Updated Event #{event_id}."
        }

    # --- FILE MANAGER TOOLS ---

    def search_files(self, query: str = "") -> dict:
        with self._get_connection() as conn:
            q_clean = query.strip()
            if not q_clean:
                rows = conn.execute(
                    "SELECT id, filename, category, summary, keywords FROM uploaded_files ORDER BY uploaded_at DESC LIMIT 10"
                ).fetchall()
            else:
                # Detect file extension query
                ext_pattern = None
                ql = q_clean.lower()
                for ext in ["pdf", "py", "docx", "csv", "json", "js", "md", "txt"]:
                    if ext in ql or f".{ext}" in ql:
                        ext_pattern = f"%.{ext}"
                        break
                if ext_pattern:
                    rows = conn.execute(
                        "SELECT id, filename, category, summary, keywords FROM uploaded_files WHERE filename LIKE ? OR category LIKE ? OR summary LIKE ? ORDER BY uploaded_at DESC",
                        (ext_pattern, f"%{q_clean}%", f"%{q_clean}%")
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, filename, category, summary, keywords FROM uploaded_files WHERE filename LIKE ? OR category LIKE ? OR summary LIKE ? OR keywords LIKE ? OR extracted_text LIKE ? ORDER BY uploaded_at DESC",
                        (f"%{q_clean}%", f"%{q_clean}%", f"%{q_clean}%", f"%{q_clean}%", f"%{q_clean}%")
                    ).fetchall()
        files = [{"id": r[0], "filename": r[1], "category": r[2], "summary": r[3] or "", "keywords": r[4] or ""} for r in rows]
        return {
            "status": "success",
            "action": "search_files",
            "count": len(files),
            "files": files,
            "message": f"Found {len(files)} matching file(s)."
        }

    def read_file(self, file_id: int = None, filename: str = None) -> dict:
        with self._get_connection() as conn:
            if file_id:
                row = conn.execute("SELECT id, filename, extracted_text, category, summary FROM uploaded_files WHERE id = ?", (file_id,)).fetchone()
            elif filename:
                row = conn.execute("SELECT id, filename, extracted_text, category, summary FROM uploaded_files WHERE filename LIKE ? ORDER BY uploaded_at DESC LIMIT 1", (f"%{filename}%",)).fetchone()
            else:
                row = conn.execute("SELECT id, filename, extracted_text, category, summary FROM uploaded_files ORDER BY uploaded_at DESC LIMIT 1").fetchone()
        if not row:
            return {"error": "File not found."}
        return {
            "status": "success",
            "action": "read_file",
            "file_id": row[0],
            "filename": row[1],
            "category": row[3],
            "summary": row[4],
            "content": row[2] or "[No extracted text available]",
            "message": f"Read file '{row[1]}' ({len(row[2] or '')} characters)."
        }

    def summarize_file(self, file_id: int = None, filename: str = None) -> dict:
        read_res = self.read_file(file_id=file_id, filename=filename)
        if "error" in read_res:
            return read_res
        if read_res.get("summary"):
            return {
                "status": "success",
                "action": "summarize_file",
                "file_id": read_res["file_id"],
                "filename": read_res["filename"],
                "summary": read_res["summary"],
                "message": f"Summary of '{read_res['filename']}': {read_res['summary']}"
            }
        content = read_res.get("content", "")
        model, _ = self.get_gemini_model()
        if model and content:
            try:
                res = model.generate_content(f"Summarize this document in 2-3 concise sentences:\n{content[:10000]}")
                summary = res.text.strip()
            except Exception as e:
                summary = content[:200]
        else:
            summary = content[:200]
        return {
            "status": "success",
            "action": "summarize_file",
            "file_id": read_res["file_id"],
            "filename": read_res["filename"],
            "summary": summary,
            "message": f"Summary of '{read_res['filename']}': {summary}"
        }

    def ask_file_question(self, file_id: int, question: str) -> dict:
        read_res = self.read_file(file_id=file_id)
        if "error" in read_res:
            return read_res
        content = read_res.get("content", "")
        model, _ = self.get_gemini_model()
        if not model:
            return {"error": "Gemini AI model is currently offline."}
        prompt = f"""You are NEXUS AI File Intelligence. Answer this question strictly based on the file content below.
If the information is not present, state: "This information is not available in the uploaded file."
File: {read_res['filename']}
Content:
{content[:12000]}
Question: {question}"""
        try:
            res = model.generate_content(prompt)
            reply = res.text.strip()
        except Exception as e:
            reply = f"Error querying file: {str(e)}"
        return {
            "status": "success",
            "action": "ask_file_question",
            "file_id": file_id,
            "filename": read_res["filename"],
            "reply": reply,
            "message": reply
        }

    # --- DESKTOP AUTOMATION TOOLS ---

    def switch_application(self, app_name: str) -> dict:
        valid_apps = {
            "notes": "Notes",
            "task manager": "Task Manager",
            "tasks": "Task Manager",
            "calendar": "Calendar",
            "file manager": "File Manager",
            "files": "File Manager",
            "ai assistant": "AI Assistant",
            "chat": "AI Assistant",
            "ai agent dashboard": "AI Agent Dashboard",
            "agent": "AI Agent Dashboard",
            "calculator": "Calculator",
            "system monitor": "System Monitor",
            "settings": "Settings"
        }
        target = valid_apps.get(app_name.lower().strip())
        if not target:
            target = "AI Agent Dashboard"
        return {
            "status": "success",
            "action": "switch_application",
            "target_app": target,
            "client_action": {"action": "open_app", "target": target},
            "message": f"Navigated to {target}."
        }

    # --- IMAGE GENERATION TOOLS ---

    def generate_image(self, prompt: str, aspect_ratio: str = "1:1") -> dict:
        if not prompt or not prompt.strip():
            return {"error": "Image prompt cannot be empty."}
        import uuid
        import app as backend_app
        img_bytes, ext, model_used = backend_app.generate_ai_image(prompt.strip(), aspect_ratio)
        if not img_bytes:
            return {"error": f"Failed to generate image: {model_used or 'Provider unavailable'}"}

        filename = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.{ext}"
        filepath = os.path.join(backend_app.IMAGES_FOLDER, filename)
        with open(filepath, "wb") as f:
            f.write(img_bytes)

        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO generated_images (prompt, filename, filepath, aspect_ratio, created_at) VALUES (?, ?, ?, ?, ?)",
                (prompt.strip(), filename, filepath, aspect_ratio, now)
            )
            img_id = cur.lastrowid
            conn.commit()

        return {
            "status": "success",
            "action": "generate_image",
            "client_action": {"action": "open_app", "target": "AI Assistant"},
            "image_id": img_id,
            "filename": filename,
            "url": f"/api/images/{filename}",
            "prompt": prompt.strip(),
            "model": model_used,
            "message": f"Generated image for: '{prompt.strip()}'"
        }

    # --- INTERNAL DATE HELPERS ---

    def _parse_date_string(self, s: str) -> str:
        now = datetime.now()
        sl = str(s).lower().strip()
        if "tomorrow" in sl:
            return (now + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "today" in sl:
            return now.strftime("%Y-%m-%d")
        elif "next week" in sl:
            return (now + timedelta(days=7)).strftime("%Y-%m-%d")
        for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y", "%d/%m/%Y"]:
            try:
                return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
            except Exception:
                continue
        return s.strip()

    def _parse_datetime_string(self, s: str, default_hour: int = 15) -> str:
        now = datetime.now()
        sl = str(s).lower().strip()
        target = now
        if "tomorrow" in sl:
            target = now + timedelta(days=1)
        elif "today" in sl:
            target = now
        elif "next week" in sl:
            target = now + timedelta(days=7)

        # Parse hour/time if specified
        match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', sl)
        if match:
            h = int(match.group(1))
            m = int(match.group(2) or 0)
            meridiem = match.group(3)
            if meridiem == "pm" and h < 12:
                h += 12
            elif meridiem == "am" and h == 12:
                h = 0
            return target.replace(hour=h, minute=m, second=0, microsecond=0).isoformat()
        return target.replace(hour=default_hour, minute=0, second=0, microsecond=0).isoformat()

    def _add_hours(self, dt_iso: str, hours: int = 1) -> str:
        try:
            dt = datetime.fromisoformat(dt_iso)
            return (dt + timedelta(hours=hours)).isoformat()
        except Exception:
            return dt_iso


# ==============================================================================
# 3. EXECUTION LOGGER
# ==============================================================================

class ExecutionLogger:
    """Maintains an execution history of all agent activities in SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
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
            conn.commit()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def log_execution(self, command: str, intent: str, tools_called: list, status: str, result: str, client_actions: list = None, execution_time_ms: int = 0) -> int:
        now = datetime.now().isoformat()
        tools_json = json.dumps(tools_called)
        actions_json = json.dumps(client_actions or [])
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO agent_logs (timestamp, command, intent, tools_called, status, result, client_actions, execution_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now, command, intent, tools_json, status, result, actions_json, execution_time_ms)
            )
            log_id = cur.lastrowid
            conn.commit()
        return log_id

    def get_recent_logs(self, limit: int = 30) -> list:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, command, intent, tools_called, status, result, client_actions, execution_time_ms FROM agent_logs ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        logs = []
        for r in rows:
            try:
                tools = json.loads(r[4])
            except Exception:
                tools = [r[4]]
            try:
                actions = json.loads(r[7])
            except Exception:
                actions = []
            logs.append({
                "id": r[0],
                "timestamp": r[1],
                "command": r[2],
                "intent": r[3],
                "tools_called": tools,
                "status": r[5],
                "result": r[6],
                "client_actions": actions,
                "execution_time_ms": r[8]
            })
        return logs

    def get_metrics(self) -> dict:
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM agent_logs").fetchone()[0]
            success = conn.execute("SELECT COUNT(*) FROM agent_logs WHERE status = 'SUCCESS'").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM agent_logs WHERE status = 'FAILED'").fetchone()[0]
            confirmation = conn.execute("SELECT COUNT(*) FROM agent_logs WHERE status = 'CONFIRMATION_REQUIRED'").fetchone()[0]
            recent = conn.execute("SELECT command, intent, status, timestamp FROM agent_logs ORDER BY id DESC LIMIT 1").fetchone()
        rate = round((success / total * 100), 1) if total > 0 else 100.0
        return {
            "total_commands": total,
            "success_count": success,
            "failed_count": failed,
            "confirmation_count": confirmation,
            "success_rate": f"{rate}%",
            "last_activity": {
                "command": recent[0] if recent else "System Idle",
                "intent": recent[1] if recent else "NONE",
                "status": recent[2] if recent else "READY",
                "timestamp": recent[3] if recent else datetime.now().isoformat()
            } if recent else None
        }


# ==============================================================================
# 4. AI AGENT ENGINE (Orchestrator)
# ==============================================================================

class AIAgentEngine:
    """Coordinates Intent Parsing, Multi-Step Planning, Tool Execution, and Verification."""

    def __init__(self, db_path: str, upload_folder: str, get_gemini_model_fn):
        self.db_path = db_path
        self.upload_folder = upload_folder
        self.get_gemini_model = get_gemini_model_fn
        self.tools = ApplicationTools(db_path, upload_folder, get_gemini_model_fn)
        self.logger = ExecutionLogger(db_path)

    def execute_command(self, command: str, conversation_id: int = None, confirmed: bool = False) -> dict:
        start_time = time.time()
        cmd_clean = command.strip()
        if not cmd_clean:
            return {"error": "Empty command provided."}

        # Step 1: Detect Intent and Plan Tool Steps via Gemini
        plan = self._plan_command(cmd_clean)
        intent = plan.get("intent", "GENERAL_CHAT")
        steps = plan.get("steps", [])
        thought = plan.get("thought", "")

        # If general chat or clarification needed without tools
        if not steps or intent == "GENERAL_CHAT":
            reply = plan.get("reply") or plan.get("clarification_prompt") or "I understand. How else can I assist your desktop?"
            duration_ms = int((time.time() - start_time) * 1000)
            self.logger.log_execution(cmd_clean, intent, [], "SUCCESS", reply, [], duration_ms)
            return {
                "status": "success",
                "intent": intent,
                "thought": thought,
                "actions_executed": [],
                "client_actions": [],
                "reply": reply,
                "duration_ms": duration_ms
            }

        executed_actions = []
        client_actions = []
        tools_called = []
        context_data = {}

        # Step 2: Execute Tool Steps Sequentially (Multi-Step Pipeline)
        for idx, step in enumerate(steps, 1):
            tool_name = step.get("tool")
            params = step.get("parameters", {})
            tools_called.append(tool_name)

            # Check if this tool requires prior context (e.g. file_id from a search_files step)
            if "file_id" in params and params["file_id"] in [None, "", "auto"] and "last_file_id" in context_data:
                params["file_id"] = context_data["last_file_id"]

            # Destructive confirmation check
            if PermissionManager.is_destructive(tool_name) and not confirmed:
                allowed, prompt_msg = PermissionManager.check_permission(tool_name, params, confirmed=False)
                duration_ms = int((time.time() - start_time) * 1000)
                self.logger.log_execution(cmd_clean, intent, tools_called, "CONFIRMATION_REQUIRED", prompt_msg, [], duration_ms)
                return {
                    "status": "confirmation_required",
                    "intent": intent,
                    "thought": thought,
                    "tool": tool_name,
                    "parameters": params,
                    "confirmation_prompt": prompt_msg,
                    "actions_executed": executed_actions,
                    "client_actions": [],
                    "reply": f"⚠️ **Permission Required**\n\n{prompt_msg}\n\n*Please confirm to execute this action.*",
                    "duration_ms": duration_ms
                }

            # Dispatch tool
            action_result = self._dispatch_tool(tool_name, params, confirmed)
            executed_actions.append({
                "step": idx,
                "tool": tool_name,
                "description": step.get("description", tool_name),
                "parameters": params,
                "result": action_result
            })

            # Track client actions (e.g. desktop window switching)
            if "client_action" in action_result:
                client_actions.append(action_result["client_action"])

            # Pipe context to subsequent steps
            if tool_name == "search_files" and action_result.get("files"):
                context_data["last_file_id"] = action_result["files"][0]["id"]
                context_data["last_filename"] = action_result["files"][0]["filename"]
            elif tool_name == "create_note" and action_result.get("note_id"):
                context_data["last_note_id"] = action_result["note_id"]
            elif tool_name == "create_task" and action_result.get("task_id"):
                context_data["last_task_id"] = action_result["task_id"]

        # Step 3: Synthesize Final User-Facing Response
        duration_ms = int((time.time() - start_time) * 1000)
        formatted_reply = self._synthesize_response(cmd_clean, intent, thought, executed_actions)

        # Step 4: Record Execution Log in SQLite
        status_code = "SUCCESS" if all("error" not in a.get("result", {}) for a in executed_actions) else "FAILED"
        self.logger.log_execution(cmd_clean, intent, tools_called, status_code, formatted_reply, client_actions, duration_ms)

        return {
            "status": "success" if status_code == "SUCCESS" else "partial_error",
            "intent": intent,
            "thought": thought,
            "tools_called": tools_called,
            "actions_executed": executed_actions,
            "client_actions": client_actions,
            "reply": formatted_reply,
            "duration_ms": duration_ms
        }

    def _dispatch_tool(self, tool_name: str, params: dict, confirmed: bool) -> dict:
        try:
            # Notes
            if tool_name == "create_note":
                return self.tools.create_note(content=params.get("content", ""))
            elif tool_name == "search_notes":
                return self.tools.search_notes(query=params.get("query", ""))
            elif tool_name == "edit_note":
                return self.tools.edit_note(note_id=int(params.get("note_id")), content=params.get("content", ""))
            elif tool_name == "delete_note":
                return self.tools.delete_note(note_id=int(params.get("note_id")), confirmed=confirmed)
            elif tool_name == "summarize_note":
                return self.tools.summarize_note(note_id=int(params.get("note_id")))

            # Tasks
            elif tool_name == "create_task":
                return self.tools.create_task(
                    title=params.get("title", ""),
                    priority=params.get("priority", "Medium"),
                    due_date=params.get("due_date", "")
                )
            elif tool_name == "list_tasks":
                return self.tools.list_tasks(status=params.get("status", "pending"))
            elif tool_name == "complete_task":
                return self.tools.complete_task(task_id=int(params.get("task_id")))
            elif tool_name == "delete_task":
                return self.tools.delete_task(task_id=int(params.get("task_id") or params.get("id")), confirmed=confirmed)
            elif tool_name == "update_task":
                return self.tools.update_task(
                    task_id=int(params.get("task_id") or params.get("id")),
                    title=params.get("title"),
                    priority=params.get("priority"),
                    due_date=params.get("due_date"),
                    completed=params.get("completed")
                )

            # Calendar
            elif tool_name == "create_event":
                return self.tools.create_event(
                    title=params.get("title", ""),
                    start=params.get("start", ""),
                    end=params.get("end", "")
                )
            elif tool_name == "list_events":
                return self.tools.list_events(filter_type=params.get("filter_type", "upcoming"))
            elif tool_name == "delete_event":
                return self.tools.delete_event(event_id=int(params.get("event_id") or params.get("id")), confirmed=confirmed)
            elif tool_name == "update_event":
                return self.tools.update_event(
                    event_id=int(params.get("event_id") or params.get("id")),
                    title=params.get("title"),
                    start=params.get("start"),
                    end=params.get("end")
                )

            # Files
            elif tool_name == "search_files":
                return self.tools.search_files(query=params.get("query", ""))
            elif tool_name == "read_file":
                return self.tools.read_file(
                    file_id=int(params.get("file_id")) if params.get("file_id") else None,
                    filename=params.get("filename")
                )
            elif tool_name == "summarize_file":
                return self.tools.summarize_file(
                    file_id=int(params.get("file_id")) if params.get("file_id") else None,
                    filename=params.get("filename")
                )
            elif tool_name == "ask_file_question":
                return self.tools.ask_file_question(
                    file_id=int(params.get("file_id")),
                    question=params.get("question", "")
                )

            # Desktop Automation
            elif tool_name == "switch_application":
                return self.tools.switch_application(app_name=params.get("app_name", ""))

            # Real AI Image Generation
            elif tool_name == "generate_image":
                return self.tools.generate_image(
                    prompt=params.get("prompt", ""),
                    aspect_ratio=params.get("aspect_ratio", "1:1")
                )

            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            return {"error": f"Tool execution failed for '{tool_name}': {str(e)}"}

    def _plan_command(self, command: str) -> dict:
        now_str = datetime.now().isoformat()
        today_date = datetime.now().strftime("%Y-%m-%d")
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_3pm = (datetime.now() + timedelta(days=1)).replace(hour=15, minute=0, second=0).isoformat()
        tomorrow_4pm = (datetime.now() + timedelta(days=1)).replace(hour=16, minute=0, second=0).isoformat()

        # Fast-path for direct image commands
        low = command.lower()
        if any(kw in low for kw in ["generate image", "create image", "generate an image", "create an image", "draw an image", "generate artwork", "generate picture"]):
            return self._fallback_deterministic_plan(command)

        model, _ = self.get_gemini_model()
        if not model:
            # Fallback deterministic parser if Gemini unavailable
            return self._fallback_deterministic_plan(command)

        prompt = f"""You are the NEXUS AI Agent Brain. You control the NEXUS AI Operating System.
Your job is to parse the user's natural language command, identify the intent, and output a structured tool execution plan.

TEMPORAL CONTEXT:
- Current Local Time: {now_str}
- Today's Date: {today_date}
- Tomorrow's Date: {tomorrow_date}
- Tomorrow at 3 PM: start="{tomorrow_3pm}", end="{tomorrow_4pm}"

INTENTS AVAILABLE:
CREATE, READ, UPDATE, DELETE, SEARCH, SUMMARIZE, SCHEDULE, COMPLETE, MULTI_STEP, GENERAL_CHAT, GENERATE_IMAGE

AVAILABLE TOOLS:
1. Notes:
   - create_note(content: str)
   - search_notes(query: str)
   - edit_note(note_id: int, content: str)
   - delete_note(note_id: int)
   - summarize_note(note_id: int)

2. Tasks:
   - create_task(title: str, priority: "Low"|"Medium"|"High", due_date: str)
   - list_tasks(status: "pending"|"completed"|"all")
   - complete_task(task_id: int)
   - delete_task(task_id: int)

3. Calendar:
   - create_event(title: str, start: ISO_DATETIME, end: ISO_DATETIME)
   - list_events(filter_type: "upcoming"|"today")
   - delete_event(event_id: int)

4. File Manager:
   - search_files(query: str)
   - read_file(file_id: int, filename: str)
   - summarize_file(file_id: int, filename: str)
   - ask_file_question(file_id: int, question: str)

5. Desktop Automation:
   - switch_application(app_name: "Notes"|"Task Manager"|"Calendar"|"File Manager"|"AI Agent Dashboard"|"AI Assistant")

6. Image Studio:
   - generate_image(prompt: str, aspect_ratio: "1:1"|"16:9"|"4:3"|"9:16")

OUTPUT FORMAT:
Respond ONLY with a valid JSON object (no markdown fences, no backticks):
{{
  "intent": "IntentName",
  "thought": "Reasoning about what the user wants to accomplish",
  "steps": [
    {{
      "step": 1,
      "tool": "tool_name",
      "parameters": {{ ... }},
      "description": "Short description of action"
    }}
  ],
  "clarification_needed": false,
  "clarification_prompt": ""
}}

If the command is just casual conversation (e.g. "Hello", "Who are you?"), set "intent": "GENERAL_CHAT" and "steps": [], and provide a conversational "reply".

User Command: "{command}"
"""
        try:
            res = model.generate_content(prompt)
            raw = res.text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            plan = json.loads(raw)
            return plan
        except Exception as e:
            return self._fallback_deterministic_plan(command)

    def _fallback_deterministic_plan(self, command: str) -> dict:
        """Deterministic pattern matcher when LLM is unavailable or for instant handling."""
        cl = command.lower()
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_3pm = (datetime.now() + timedelta(days=1)).replace(hour=15, minute=0, second=0).isoformat()
        tomorrow_4pm = (datetime.now() + timedelta(days=1)).replace(hour=16, minute=0, second=0).isoformat()

        # Multi-step: meeting note AND schedule event
        if "note" in cl and ("event" in cl or "meeting" in cl or "schedule" in cl) and ("and" in cl or "&" in cl):
            return {
                "intent": "MULTI_STEP",
                "thought": "Create note and schedule event workflow.",
                "steps": [
                    {"step": 1, "tool": "create_note", "parameters": {"content": "Meeting Note: " + command}, "description": "Create meeting note"},
                    {"step": 2, "tool": "create_event", "parameters": {"title": "Project Meeting", "start": tomorrow_3pm, "end": tomorrow_4pm}, "description": "Schedule meeting event"},
                    {"step": 3, "tool": "switch_application", "parameters": {"app_name": "Calendar"}, "description": "Navigate to Calendar"}
                ]
            }

        # Multi-step: find file AND summarize it
        if ("find" in cl or "search" in cl) and ("summarize" in cl or "summary" in cl):
            query = "pdf" if "pdf" in cl else ("python" if "python" in cl or "py" in cl else "")
            return {
                "intent": "MULTI_STEP",
                "thought": "Search for document and generate summary.",
                "steps": [
                    {"step": 1, "tool": "search_files", "parameters": {"query": query}, "description": f"Search files for '{query}'"},
                    {"step": 2, "tool": "summarize_file", "parameters": {"file_id": "auto"}, "description": "Summarize matching file"}
                ]
            }

        # Note creation
        if cl.startswith("create a note") or cl.startswith("add a note") or "create note" in cl or "take a note" in cl:
            content = re.sub(r"^(?:create|add|take)\s+(?:a\s+)?note\s+(?:about|on|for)?\s*", "", command, flags=re.IGNORECASE).strip()
            return {
                "intent": "CREATE",
                "thought": "Create a new note.",
                "steps": [
                    {"step": 1, "tool": "create_note", "parameters": {"content": content or command}, "description": "Create note"},
                    {"step": 2, "tool": "switch_application", "parameters": {"app_name": "Notes"}, "description": "Open Notes app"}
                ]
            }

        # Task creation
        if "task" in cl and ("create" in cl or "add" in cl or "new" in cl or "priority" in cl):
            priority = "High" if "high" in cl else ("Low" if "low" in cl else "Medium")
            due = tomorrow_date if "tomorrow" in cl else ""
            title = re.sub(r"^(?:create|add)\s+(?:a\s+)?(?:high-priority|low-priority|medium-priority)?\s*task\s*(?:for|to|about)?\s*", "", command, flags=re.IGNORECASE).strip()
            return {
                "intent": "CREATE",
                "thought": "Create a new task.",
                "steps": [
                    {"step": 1, "tool": "create_task", "parameters": {"title": title or command, "priority": priority, "due_date": due}, "description": f"Create {priority} priority task"},
                    {"step": 2, "tool": "switch_application", "parameters": {"app_name": "Task Manager"}, "description": "Open Task Manager"}
                ]
            }

        # Pending tasks search
        if "pending task" in cl or "show task" in cl or "list task" in cl or "my tasks" in cl:
            return {
                "intent": "READ",
                "thought": "List pending tasks.",
                "steps": [
                    {"step": 1, "tool": "list_tasks", "parameters": {"status": "pending"}, "description": "Fetch pending tasks"},
                    {"step": 2, "tool": "switch_application", "parameters": {"app_name": "Task Manager"}, "description": "View Task Manager"}
                ]
            }

        # Event creation / Scheduling
        if "schedule" in cl or "event" in cl or "calendar" in cl:
            title = re.sub(r"^(?:schedule|create)\s+(?:an?\s+)?(?:event|meeting)?\s*(?:for|at)?\s*", "", command, flags=re.IGNORECASE).strip()
            return {
                "intent": "SCHEDULE",
                "thought": "Schedule an event.",
                "steps": [
                    {"step": 1, "tool": "create_event", "parameters": {"title": title or "Scheduled Event", "start": tomorrow_3pm, "end": tomorrow_4pm}, "description": "Create calendar event"},
                    {"step": 2, "tool": "switch_application", "parameters": {"app_name": "Calendar"}, "description": "Open Calendar"}
                ]
            }

        # Delete operations (Destructive Actions)
        m_del_task = re.search(r"(?:delete|remove)\s+(?:task|todo)\s+#?(\d+)", cl)
        if m_del_task:
            tid = int(m_del_task.group(1))
            return {
                "intent": "DELETE",
                "thought": f"Delete task #{tid}",
                "steps": [
                    {"step": 1, "tool": "delete_task", "parameters": {"task_id": tid}, "description": f"Delete task #{tid}"}
                ]
            }

        m_del_note = re.search(r"(?:delete|remove)\s+note\s+#?(\d+)", cl)
        if m_del_note:
            nid = int(m_del_note.group(1))
            return {
                "intent": "DELETE",
                "thought": f"Delete note #{nid}",
                "steps": [
                    {"step": 1, "tool": "delete_note", "parameters": {"note_id": nid}, "description": f"Delete note #{nid}"}
                ]
            }

        m_del_event = re.search(r"(?:delete|remove|cancel)\s+(?:event|meeting)\s+#?(\d+)", cl)
        if m_del_event:
            eid = int(m_del_event.group(1))
            return {
                "intent": "DELETE",
                "thought": f"Delete event #{eid}",
                "steps": [
                    {"step": 1, "tool": "delete_event", "parameters": {"event_id": eid}, "description": f"Delete event #{eid}"}
                ]
            }

        # Complete task
        if "complete" in cl or "done" in cl:
            tid_match = re.search(r"\d+", cl)
            if tid_match:
                tid = int(tid_match.group(0))
                return {
                    "intent": "COMPLETE",
                    "thought": f"Complete task #{tid}",
                    "steps": [
                        {"step": 1, "tool": "complete_task", "parameters": {"task_id": tid}, "description": f"Mark task #{tid} as completed"}
                    ]
                }

        # Image Generation
        if any(w in cl for w in ["generate image", "create image", "draw image", "make an image", "generate an image", "picture of", "photo of"]):
            prompt_clean = re.sub(r'^(?:please\s+)?(?:can\s+you\s+)?(?:generate|create|draw|make|render)\s+(?:an?\s+)?(?:image|picture|photo)\s+(?:of\s+)?', '', command, flags=re.IGNORECASE).strip()
            return {
                "intent": "GENERATE_IMAGE",
                "thought": "Generate AI image.",
                "steps": [
                    {"step": 1, "tool": "generate_image", "parameters": {"prompt": prompt_clean or command, "aspect_ratio": "1:1"}, "description": f"Generate image for '{prompt_clean or command}'"}
                ]
            }

        # Default fallback
        return {
            "intent": "GENERAL_CHAT",
            "thought": "General conversational query.",
            "steps": [],
            "reply": f"I am your NEXUS AI Agent. I received your request: '{command}'. I can create notes, manage tasks, schedule calendar events, and interrogate files. What would you like me to do?"
        }

    def _synthesize_response(self, command: str, intent: str, thought: str, actions: list) -> str:
        lines = []
        lines.append(f"**⚡ NEXUS AI Agent Execution** | Intent: `{intent}`\n")

        lines.append("### ⚙️ Executed Actions:")
        for action in actions:
            step_no = action["step"]
            desc = action["description"]
            res = action["result"]

            if "error" in res:
                lines.append(f"- ❌ **Step {step_no}:** {desc} — *Error: {res['error']}*")
            elif res.get("status") == "confirmation_required":
                lines.append(f"- ⚠️ **Step {step_no}:** {desc} — *Confirmation Required*")
            else:
                msg = res.get("message") or "Completed successfully."
                lines.append(f"- ✅ **Step {step_no}:** {desc} — {msg}")

        lines.append("\n### 💬 Summary:")
        # Provide specific friendly confirmation based on actions
        summary_points = []
        for a in actions:
            r = a["result"]
            if a["tool"] == "create_note" and "note_id" in r:
                summary_points.append(f"Saved note #{r['note_id']}")
            elif a["tool"] == "create_task" and "task_id" in r:
                summary_points.append(f"Added task #{r['task_id']} ({r.get('priority')} Priority)")
            elif a["tool"] == "create_event" and "event_id" in r:
                summary_points.append(f"Scheduled event #{r['event_id']}")
            elif a["tool"] == "list_tasks" and "tasks" in r:
                t_count = len(r['tasks'])
                if t_count == 0:
                    summary_points.append("You have no pending tasks.")
                else:
                    t_list = ", ".join(f"\"{t['title']}\" ({t['priority']})" for t in r['tasks'][:3])
                    summary_points.append(f"You have {t_count} pending task(s): {t_list}")
            elif a["tool"] == "summarize_file" and "summary" in r:
                summary_points.append(f"**{r.get('filename')} Summary:** {r.get('summary')}")
            elif a["tool"] == "switch_application":
                summary_points.append(f"Navigated desktop to **{r.get('target_app')}**")
            elif a["tool"] == "generate_image" and "url" in r:
                summary_points.append(f"Generated Image: [{r.get('prompt')}]({r.get('url')})\n\n<div class='generated-image-card'><img src='{r.get('url')}' style='max-width:320px; border-radius:8px; border:1px solid #7c3aed; margin-top:8px;' /><br/><a href='{r.get('url')}' download='{r.get('filename')}' class='nexus-btn' style='display:inline-block; margin-top:6px; font-size:11px; padding:3px 8px; text-decoration:none;'>⬇️ Download Image</a></div>")

        if summary_points:
            lines.append(" • " + "\n • ".join(summary_points))
        else:
            lines.append("All requested operations completed successfully.")

        return "\n".join(lines)
