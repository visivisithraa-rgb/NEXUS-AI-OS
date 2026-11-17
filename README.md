# ✦ NEXUS AI OS

**NEXUS AI OS** is a modern, AI-powered desktop operating system interface running on a Python Flask backend with persistent SQLite storage and an aesthetic purple dark theme.

---

## 🚀 Features & Applications

1. **🤖 AI Assistant**:
   - Integrated with Google Gemini AI (`gemini-1.5-flash` / `gemini-pro`).
   - Multi-session conversation management (New Chat, Delete Chat, Clear).
   - Rich Markdown rendering with code block formatting and instant **📋 Copy** buttons.
   - **🔄 One-Click Retry** button when an error occurs.
   - Voice assistant with browser Web Speech API (speech-to-text `🎤` and text-to-speech output).
   - Animated typing indicators and timestamps.

2. **🚀 App Launcher & Spotlight**:
   - Spotlight overlay activated via the sidebar button or keyboard shortcut (`Ctrl + Space` / `Alt + Space`).
   - Real-time search across all 9 built-in OS applications.
   - Instant keyboard navigation: press Enter to launch any highlighted app.
   - Quick dismiss via `Esc`.

2. **📁 File Manager**:
   - Persistent backend file upload (`POST /api/files/upload`).
   - File listing with size metadata and upload dates.
   - Direct download links (`/api/files/<filename>`).
   - In-browser file preview for text, Markdown, JSON, and images.

3. **📝 Notes**:
   - Full CRUD operations connected to SQLite.
   - Real-time instant search bar (`🔍 Search notes...`).
   - Editable note cards with timestamps and status toasts.

4. **📋 Task Manager**:
   - Task creation with priorities (`Low`, `Medium`, `High`) and optional due dates.
   - Interactive completion checkboxes (`completed` / `pending`).
   - Dynamic counters for **Total**, **Pending**, and **Completed** tasks.
   - Multi-filter controls (Search, Status, Priority).

5. **📅 Calendar**:
   - Interactive monthly calendar grid with month navigation (**◀ Prev**, **Next ▶**, **Today**).
   - Event scheduling with start/end time validation.
   - Event indicator dots on days with scheduled events.
   - Upcoming events list with edit and delete actions.

6. **🧮 Calculator**:
   - Functional arithmetic calculator with decimals, percentage, and negation.
   - Supports button clicks and clean expression display.

7. **📊 System Monitor**:
   - Live telemetry for Core Backend status, SQLite database connectivity, and DB size.
   - Host platform runtime specifications (OS & Python version).
   - Real-time resource counts (Notes, Tasks, Events, Files, Conversations).

8. **⚙️ Settings & Preferences**:
   - Desktop Theme Switcher (**Purple Dark**, **Deep Blue Neon**, **Emerald Matrix**).
   - Custom User Display Name profile badge.
   - Clock Format (12-hour AM/PM vs 24-hour military format).
   - Voice response default toggle.

9. **🔔 Notification Center**:
   - Desktop toast alerts for note actions, task updates, event additions, and file uploads.
   - Notification history panel accessible via the header bell icon.

---

## 🛠️ Project Structure

```text
NEXUS-AI-OS/
├── app.py                 # Flask REST API backend & static server
├── index.html             # OS desktop layout & application window
├── style.css              # Purple dark UI stylesheet & themes
├── script.js              # Frontend application logic & state
├── requirements.txt       # Python dependencies
├── .env.example           # Example environment template
├── .env                   # Active environment variables (API keys)
├── .gitignore             # Git ignore file
├── database/
│   └── nexus.db           # SQLite database
└── uploads/               # Stored uploaded files
```

---

## ⚡ Quickstart Guide

### 1. Prerequisites
- Python 3.10+ installed
- Modern web browser (Chrome, Edge, Firefox, or Safari)

### 2. Configure Environment
Add your Google Gemini API key to the `.env` file:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```
*(Get a free API key at [Google AI Studio](https://aistudio.google.com/app/apikey))*

### 3. Start the Backend Server
Using the included virtual environment:
```powershell
.\.venv\Scripts\python.exe -u app.py
```
Or with standard Python:
```bash
python app.py
```

### 4. Open NEXUS AI OS
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 🔌 API Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/status` | Backend health & database status |
| `GET` | `/api/system/info` | Detailed system and telemetry metrics |
| `POST` | `/api/chat` | AI chat endpoint with conversation memory |
| `GET` | `/api/conversations` | List all saved chat conversations |
| `POST` | `/api/conversations` | Create a new conversation |
| `DELETE`| `/api/conversations/<id>` | Delete conversation and messages |
| `GET` | `/api/notes` | List all notes |
| `POST` | `/api/notes` | Create a new note |
| `PUT` | `/api/notes/<id>` | Update an existing note |
| `DELETE`| `/api/notes/<id>` | Delete a note |
| `GET` | `/api/tasks` | List all tasks |
| `POST` | `/api/tasks` | Create a task (priority, due date) |
| `PUT` | `/api/tasks/<id>` | Update a task or toggle completion |
| `DELETE`| `/api/tasks/<id>` | Delete a task |
| `GET` | `/api/events` | List calendar events |
| `POST` | `/api/events` | Create a calendar event |
| `PUT` | `/api/events/<id>` | Update a calendar event |
| `DELETE`| `/api/events/<id>` | Delete a calendar event |
| `GET` | `/api/files` | List uploaded files |
| `POST` | `/api/files/upload` | Upload a file to persistent storage |
| `GET` | `/api/files/<name>` | Download a file |
