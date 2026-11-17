// =================================
// NEXUS AI OS - CLOCK
// =================================

function updateClock() {
    const clockEl = document.getElementById("clock");
    if (!clockEl) return;
    const format = localStorage.getItem("nexusClockFormat") || "12";
    const now = new Date();
    if (format === "24") {
        clockEl.textContent = `${now.toLocaleDateString()} ${now.toLocaleTimeString([], { hour12: false })}`;
    } else {
        clockEl.textContent = now.toLocaleString();
    }
}

function updateProfileBadge() {
    const badge = document.getElementById("userProfileBadge");
    if (!badge) return;
    const name = localStorage.getItem("nexusUserName") || "Commander";
    badge.textContent = `👤 ${name}`;
}

// =================================
// AI CONFIGURATION STATUS MONITOR
// =================================

async function checkAiConfigStatus() {
    const badge = document.getElementById("aiConfigStatusBadge");
    const taskbarBadge = document.getElementById("taskbarAiStatus");
    try {
        const res = await fetch("/api/ai/status");
        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        if (data && data.configured) {
            if (badge) {
                badge.className = "ai-config-badge configured";
                badge.textContent = "Configuration Ready";
                const details = [];
                if (data.provider) details.push(`Provider: ${data.provider}`);
                if (data.model) details.push(`Model: ${data.model}`);
                badge.title = details.length ? details.join(" | ") : "AI configuration is ready.";
            }
            if (taskbarBadge) {
                taskbarBadge.textContent = "AI: Configuration Ready";
                taskbarBadge.style.color = "#4ade80";
            }
        } else {
            if (badge) {
                badge.className = "ai-config-badge not-configured";
                badge.textContent = "Not Configured";
                badge.title = (data && data.message) ? data.message : "AI provider is not configured yet.";
            }
            if (taskbarBadge) {
                taskbarBadge.textContent = "AI: Not Configured";
                taskbarBadge.style.color = "#f6ad55";
            }
        }
    } catch (err) {
        if (badge) {
            badge.className = "ai-config-badge error";
            badge.textContent = "Connection Error";
            badge.title = `Backend connection failed: ${err.message}`;
        }
        if (taskbarBadge) {
            taskbarBadge.textContent = "AI: Connection Error";
            taskbarBadge.style.color = "#ff5c7c";
        }
    }
}

setInterval(updateClock, 1000);
updateClock();
updateProfileBadge();
checkAiConfigStatus();

// =================================
// OPEN APPLICATIONS
// =================================

let isMaximized = false;
let runningApps = new Set();
let activeApp = null;

function openApp(appName) {
    const win = document.getElementById("appWindow");
    const title = document.getElementById("windowTitle");
    const content = document.getElementById("windowContent");

    activeApp = appName;
    runningApps.add(appName);
    updateTaskbarApps();

    title.textContent = appName;
    win.hidden = false;

    // Load the appropriate application UI
    if (appName === "AI Assistant") {
        win.classList.add("assistant-window-expanded");
        renderAssistantUI();
    } else {
        win.classList.remove("assistant-window-expanded");
        if (appName === "AI Agent Dashboard" || appName === "AI Agent") {
            showAgentDashboard();
        } else if (appName === "File Manager") {
            showFileManager();
        } else if (appName === "Notes") {
            showNotes();
        } else if (appName === "Settings") {
            showSettings();
        } else if (appName === "Task Manager") {
            showTaskManager();
        } else if (appName === "Calendar") {
            showCalendar();
        } else if (appName === "Calculator") {
            showCalculator();
        } else if (appName === "System Monitor") {
            showSystemMonitor();
        } else if (appName === "Notification Center") {
            showNotificationCenter();
        }
    }
}

// =================================
// AI ASSISTANT APPLICATION (Phase 7: Gemini Experience)
// =================================

let savedConvId = localStorage.getItem('nexus_current_conversation_id');
let currentConversationId = savedConvId ? parseInt(savedConvId) : null;
let voiceEnabled = localStorage.getItem('nexus_voice_enabled') === 'true';
let currentSpeakingBtn = null;
let isChatGenerating = false;
let currentAssistantTab = 'chat';
let currentGeneratedImage = null;
let asstActiveFileId = null;

// MediaRecorder Voice STT state
let mediaRecorder = null;
let audioChunks = [];
let isRecordingAudio = false;
let micAutoStopTimer = null;

// Safe Fetch Helper: Validates content-type and prevents "Unexpected token '<'" HTML parse errors
async function safeFetchJson(url, options = {}) {
    let res;
    try {
        res = await fetch(url, options);
    } catch (networkErr) {
        throw new Error(`Network error: ${networkErr.message}`);
    }

    const contentType = (res.headers.get("content-type") || "").toLowerCase();
    let data;
    if (contentType.includes("application/json")) {
        try {
            data = await res.json();
        } catch (jsonErr) {
            data = { error: `Invalid JSON returned by server: ${jsonErr.message}` };
        }
    } else {
        const text = await res.text().catch(() => "");
        let cleanMsg = text.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
        if (cleanMsg.length > 140) cleanMsg = cleanMsg.slice(0, 140) + "...";
        data = { error: cleanMsg || `Server returned non-JSON response (${res.status})` };
    }

    if (!res.ok) {
        throw new Error(data.error || `Request failed with HTTP ${res.status}`);
    }
    return data;
}

function setCurrentConversationId(id) {
    currentConversationId = id ? parseInt(id) : null;
    if (currentConversationId) {
        localStorage.setItem('nexus_current_conversation_id', currentConversationId);
    } else {
        localStorage.removeItem('nexus_current_conversation_id');
    }
}

function formatRelativeDate(isoStr) {
    if (!isoStr) return '';
    try {
        const d = new Date(isoStr);
        const now = new Date();
        const diffMs = now - d;
        const diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) return `${diffHours}h ago`;
        const diffDays = Math.floor(diffHours / 24);
        if (diffDays === 1) return 'Yesterday';
        if (diffDays < 7) return `${diffDays}d ago`;
        return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch (e) {
        return '';
    }
}

function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text || "";
    return div.innerHTML;
}

function escapeJsonAttr(obj) {
    return JSON.stringify(obj).replace(/"/g, '&quot;');
}

function showToastNotification(message) {
    let toast = document.getElementById("nexusToast");
    if (!toast) {
        toast = document.createElement("div");
        toast.id = "nexusToast";
        toast.style.cssText = `
            position: fixed;
            bottom: 50px;
            right: 20px;
            background: #2a1c40;
            color: #f3e8ff;
            padding: 10px 16px;
            border-radius: 8px;
            border: 1px solid #a879e5;
            box-shadow: 0 4px 16px rgba(0,0,0,0.5);
            font-size: 13px;
            z-index: 9999;
            transition: opacity 0.3s ease, transform 0.3s ease;
            opacity: 0;
            transform: translateY(10px);
            pointer-events: none;
        `;
        document.body.appendChild(toast);
    }
    toast.innerHTML = message;
    toast.style.opacity = "1";
    toast.style.transform = "translateY(0)";
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(10px)";
    }, 3200);
}

// -----------------------------
// ASSISTANT NAVIGATION & TABS
// -----------------------------

function switchAssistantTab(tab) {
    currentAssistantTab = tab;
    const navBar = document.getElementById("assistantNavBar");
    if (navBar) {
        navBar.querySelectorAll(".assistant-tab-btn").forEach(btn => {
            if (btn.dataset.tab === tab) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });
    }

    const panels = {
        chat: document.getElementById("assistantChatView"),
        image: document.getElementById("assistantImageView"),
        files: document.getElementById("assistantFilesView"),
        history: document.getElementById("assistantHistoryView"),
        agent: document.getElementById("assistantAgentView")
    };

    Object.keys(panels).forEach(k => {
        if (panels[k]) {
            panels[k].style.display = (k === tab) ? (k === 'chat' ? 'flex' : 'block') : 'none';
        }
    });

    if (tab !== 'chat' && typeof stopSpeechRecognition === 'function') {
        stopSpeechRecognition();
    }

    if (tab === 'chat') {
        loadConversations();
        loadChatHistory();
    } else if (tab === 'image') {
        renderImageStudio();
    } else if (tab === 'files') {
        renderAssistantFilesView();
    } else if (tab === 'history') {
        renderAssistantHistoryView();
    } else if (tab === 'agent') {
        renderAssistantAgentView();
    }
}

// Render Master Assistant UI with Navigation Tabs
function renderAssistantUI() {
    const content = document.getElementById("windowContent");
    content.innerHTML = `
        <!-- Top Navigation Bar -->
        <div class="assistant-nav-bar" id="assistantNavBar">
            <button class="assistant-tab-btn ${currentAssistantTab === 'chat' ? 'active' : ''}" data-tab="chat" onclick="switchAssistantTab('chat')">
                💬 AI Chat
            </button>
            <button class="assistant-tab-btn ${currentAssistantTab === 'image' ? 'active' : ''}" data-tab="image" onclick="switchAssistantTab('image')">
                🎨 Image Studio
            </button>
            <button class="assistant-tab-btn ${currentAssistantTab === 'files' ? 'active' : ''}" data-tab="files" onclick="switchAssistantTab('files')">
                📁 File Intelligence
            </button>
            <button class="assistant-tab-btn ${currentAssistantTab === 'history' ? 'active' : ''}" data-tab="history" onclick="switchAssistantTab('history')">
                🕒 History
            </button>
            <button class="assistant-tab-btn ${currentAssistantTab === 'agent' ? 'active' : ''}" data-tab="agent" onclick="switchAssistantTab('agent')">
                ⚡ AI Agent
            </button>
        </div>

        <div id="assistantTabContainer" style="flex:1; min-height:0; display:flex; flex-direction:column;">
            <!-- TAB 1: AI Chat -->
            <div id="assistantChatView" class="assistant-container" style="display:${currentAssistantTab === 'chat' ? 'flex' : 'none'};">
                <!-- LEFT SIDEBAR: Chat History -->
                <div class="assistant-sidebar" id="assistantSidebar">
                    <button id="newChatBtn" class="nexus-btn" style="width:100%; margin-bottom:8px; padding:7px 10px; font-size:12px; font-weight:600; display:flex; align-items:center; justify-content:center; gap:6px; background:#68449b; border-color:#a879e5;">
                        <span>➕</span> New Chat
                    </button>
                    <div style="position:relative; margin-bottom:8px;">
                        <input type="text" id="conversationSearchInput" class="nexus-input" placeholder="🔍 Search chats..." style="width:100%; font-size:11px; padding:5px 8px; box-sizing:border-box;" title="Filter conversation history" />
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; padding:0 2px;">
                        <span style="font-size:10px; text-transform:uppercase; color:#9d8bb8; letter-spacing:0.5px; font-weight:600;">Chat History</span>
                        <span id="convCountBadge" style="font-size:10px; color:#c4a5ff; background:rgba(168,121,229,0.15); padding:1px 6px; border-radius:10px;">0</span>
                    </div>
                    <div id="conversationList" class="conversation-list">
                        <div style="text-align:center; padding:20px 0; color:#8e7da8; font-size:11px;">
                            Loading conversations...
                        </div>
                    </div>
                </div>

                <!-- RIGHT MAIN CHAT AREA -->
                <div class="assistant-main" id="assistantMainArea">
                    <!-- Header -->
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; padding-bottom:6px; border-bottom:1px solid #362354;">
                        <div style="display:flex; align-items:center; gap:8px; min-width:0;">
                            <h2 style="margin:0; font-size:16px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:#f3e8ff;" id="activeChatTitle">🤖 NEXUS AI Assistant</h2>
                        </div>
                        <div style="display:flex; align-items:center; gap:6px; flex-shrink:0;">
                            <button id="voiceToggleBtn" class="nexus-btn ${voiceEnabled ? 'voice-badge-active' : ''}" style="font-size:11px; padding:4px 8px;" title="Toggle text-to-speech for AI answers">
                                ${voiceEnabled ? '🔊 Voice: ON' : '🔇 Voice: OFF'}
                            </button>
                            <button id="stopSpeechBtn" class="nexus-btn" style="font-size:11px; padding:4px 8px;" title="Mute active speech">⏹️ Mute</button>
                            <button id="deleteChatBtn" class="nexus-btn nexus-btn-danger" style="font-size:11px; padding:4px 8px;" title="Delete active conversation">🗑️</button>
                        </div>
                    </div>

                    <!-- Chat Log -->
                    <div id="chatLog" style="flex:1; height:320px; overflow-y:auto; margin-bottom:8px; background:#191228; padding:12px; border-radius:8px; border:1px solid #3d2b59;">
                        <div class="chat-empty-placeholder">
                            <p style="font-size:26px; margin-bottom:6px;">✦</p>
                            <p>Loading conversation...</p>
                        </div>
                    </div>

                    <!-- Voice Status Pill / Container -->
                    <div id="micStatusBar" style="display:none; align-items:center; justify-content:space-between; background:#26183c; border:1px solid #634394; border-radius:6px; padding:6px 12px; margin-bottom:6px; font-size:11px;">
                        <div id="micStatusMsg" style="display:flex; align-items:center; gap:6px; color:#e9d8fd;">
                            <span>🎙️</span> <span>Listening...</span>
                        </div>
                        <div id="micStatusActions">
                            <button id="micStopActionBtn" class="nexus-btn" style="padding:2px 8px; font-size:10px; background:#e53e3e; border-color:#fc8181;" onclick="stopSpeechRecognition()">⏹️ Stop Listening</button>
                        </div>
                    </div>

                    <!-- Input Controls -->
                    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                        <input type="text" id="assistantUserInput" class="nexus-input" placeholder="Ask NEXUS AI or speak your question..." style="flex:1; min-width:200px;" autocomplete="off" />
                        
                        <!-- Speech Recognition Language Selector (English / Tamil) -->
                        <select id="voiceLangSelect" class="nexus-input voice-lang-select" style="width:auto; padding:6px 8px; font-size:11px; background:#221538; color:#d8b4fe; border-color:#5c3a88; cursor:pointer;" title="Speech recognition language">
                            <option value="en-IN" ${getSavedVoiceLanguage() === 'en-IN' ? 'selected' : ''}>🇮🇳 English (India)</option>
                            <option value="ta-IN" ${getSavedVoiceLanguage() === 'ta-IN' ? 'selected' : ''}>🇮🇳 தமிழ் (India)</option>
                        </select>

                        <!-- Microphone Button -->
                        <button id="micBtn" class="nexus-btn voice-mic-btn" title="Click to speak (Browser Web Speech API)" style="min-width:115px; display:flex; align-items:center; justify-content:center; gap:6px;">
                            <span id="micIcon">🎤</span> <span id="micLabel">Voice Input</span>
                        </button>
                        <button id="sendBtn" class="nexus-btn" style="min-width:68px; background:#68449b; border-color:#a879e5;">Send</button>
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px; font-size:10px; color:#8e7da8;">
                        <span id="chatStatusText" style="min-height:14px;"></span>
                        <span style="font-size:10px; color:#83709d;" title="Privacy: Web Speech API processes audio through your browser provider. No audio is recorded or stored on the server.">🔒 Client-side Web Speech • Review & edit text before sending</span>
                    </div>
                </div>
            </div>

            <!-- TAB 2: Image Studio -->
            <div id="assistantImageView" style="display:${currentAssistantTab === 'image' ? 'block' : 'none'};"></div>

            <!-- TAB 3: File Intelligence -->
            <div id="assistantFilesView" style="display:${currentAssistantTab === 'files' ? 'block' : 'none'};"></div>

            <!-- TAB 4: History -->
            <div id="assistantHistoryView" style="display:${currentAssistantTab === 'history' ? 'block' : 'none'};"></div>

            <!-- TAB 5: AI Agent -->
            <div id="assistantAgentView" style="display:${currentAssistantTab === 'agent' ? 'block' : 'none'};"></div>
        </div>
    `;

    // Bind Chat UI actions
    const sendBtn = document.getElementById("sendBtn");
    if (sendBtn) sendBtn.addEventListener('click', sendMessage);

    const newChatBtn = document.getElementById("newChatBtn");
    if (newChatBtn) newChatBtn.addEventListener('click', startNewConversation);

    const deleteChatBtn = document.getElementById("deleteChatBtn");
    if (deleteChatBtn) deleteChatBtn.addEventListener('click', deleteCurrentConversation);

    const voiceToggleBtn = document.getElementById("voiceToggleBtn");
    if (voiceToggleBtn) voiceToggleBtn.addEventListener('click', toggleVoice);

    const stopSpeechBtn = document.getElementById("stopSpeechBtn");
    if (stopSpeechBtn) stopSpeechBtn.addEventListener('click', stopAllSpeech);

    const micBtn = document.getElementById("micBtn");
    if (micBtn) micBtn.addEventListener('click', toggleVoiceInput);

    const voiceLangSelect = document.getElementById("voiceLangSelect");
    if (voiceLangSelect) {
        voiceLangSelect.value = getSavedVoiceLanguage();
        voiceLangSelect.addEventListener("change", e => {
            setSavedVoiceLanguage(e.target.value);
            const langLabel = e.target.value === 'ta-IN' ? 'தமிழ் (India)' : 'English (India)';
            showToastNotification(`🌐 Voice recognition language set to ${langLabel}`);
        });
    }

    const searchInput = document.getElementById("conversationSearchInput");
    if (searchInput) {
        let debounceTimer;
        searchInput.addEventListener("input", e => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                loadConversations(e.target.value.trim());
            }, 250);
        });
    }

    const inputEl = document.getElementById("assistantUserInput");
    if (inputEl) {
        inputEl.addEventListener("keydown", e => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }

    if (currentAssistantTab === 'chat') {
        loadConversations();
        loadChatHistory();
    } else {
        switchAssistantTab(currentAssistantTab);
    }
}

// -----------------------------
// TEXT-TO-SPEECH (TTS)
// -----------------------------

function cleanMarkdownForTTS(text) {
    if (!text) return "";
    return text
        .replace(/```[\s\S]*?```/g, "Code snippet omitted.")
        .replace(/`([^`]+)`/g, "$1")
        .replace(/#{1,6}\s+/g, "")
        .replace(/[*_]{1,3}([^*_]+)[*_]{1,3}/g, "$1")
        .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
        .replace(/>\s+/g, "")
        .replace(/^[\s*-+]\s+/gm, "")
        .replace(/\s+/g, " ")
        .trim();
}

function speakText(text, triggerBtn) {
    if (!('speechSynthesis' in window)) {
        showToastNotification("⚠️ Speech synthesis is not supported in this browser.");
        return;
    }

    if (window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
        if (currentSpeakingBtn) {
            currentSpeakingBtn.innerHTML = '🔊 Listen';
            currentSpeakingBtn = null;
        }
        if (triggerBtn && triggerBtn === currentSpeakingBtn) {
            return;
        }
    }

    const clean = cleanMarkdownForTTS(text);
    if (!clean) return;

    const utter = new SpeechSynthesisUtterance(clean);
    utter.rate = 1.0;
    utter.pitch = 1.0;

    if (triggerBtn) {
        currentSpeakingBtn = triggerBtn;
        triggerBtn.innerHTML = '⏹️ Stop';
    }

    utter.onend = () => {
        if (triggerBtn) triggerBtn.innerHTML = '🔊 Listen';
        currentSpeakingBtn = null;
    };
    utter.onerror = () => {
        if (triggerBtn) triggerBtn.innerHTML = '🔊 Listen';
        currentSpeakingBtn = null;
    };

    window.speechSynthesis.speak(utter);
}

function stopAllSpeech() {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
    }
    if (currentSpeakingBtn) {
        currentSpeakingBtn.innerHTML = '🔊 Listen';
        currentSpeakingBtn = null;
    }
}

function toggleVoice() {
    voiceEnabled = !voiceEnabled;
    localStorage.setItem('nexus_voice_enabled', voiceEnabled);
    const btn = document.getElementById('voiceToggleBtn');
    if (btn) {
        if (voiceEnabled) {
            btn.innerHTML = '🔊 Voice: ON';
            btn.classList.add('voice-badge-active');
            showToastNotification("🔊 Text-to-speech enabled for AI responses");
        } else {
            btn.innerHTML = '🔇 Voice: OFF';
            btn.classList.remove('voice-badge-active');
            stopAllSpeech();
            showToastNotification("🔇 Text-to-speech disabled");
        }
    }
}

// -----------------------------
// DAY 9 & 10: VOICE INPUT (BROWSER WEB SPEECH API)
// Legacy fallback endpoint /api/voice/transcribe preserved for non-browser/Electron environments
// -----------------------------

let activeSpeechRecognition = null;
let isStartingSpeech = false; // Guard against rapid multi-clicks
let voiceWatchdogTimer = null; // Safety timeout so status never remains stuck

function isWebSpeechSupported() {
    return ('SpeechRecognition' in window) || ('webkitSpeechRecognition' in window);
}

function getSpeechRecognitionClass() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function getSavedVoiceLanguage() {
    return localStorage.getItem('nexus_speech_lang') || 'en-IN';
}

function setSavedVoiceLanguage(lang) {
    if (lang === 'en-IN' || lang === 'ta-IN') {
        localStorage.setItem('nexus_speech_lang', lang);
        // Synchronize both window and desktop language selectors
        const winSelect = document.getElementById('voiceLangSelect');
        const deskSelect = document.getElementById('desktopVoiceLangSelect');
        if (winSelect && winSelect.value !== lang) winSelect.value = lang;
        if (deskSelect && deskSelect.value !== lang) deskSelect.value = lang;
    }
}

function setVoiceStatus(state, message = '', showRetry = false) {
    const bar = document.getElementById('micStatusBar');
    const msgEl = document.getElementById('micStatusMsg');
    const actionsEl = document.getElementById('micStatusActions');
    const micBtn = document.getElementById('micBtn');
    const micIcon = document.getElementById('micIcon');
    const micLabel = document.getElementById('micLabel');

    if (state === 'idle') {
        if (bar) bar.style.display = 'none';
        if (micBtn) {
            micBtn.classList.remove('mic-recording');
            micBtn.disabled = false;
        }
        if (micIcon) micIcon.textContent = '🎤';
        if (micLabel) micLabel.textContent = 'Voice Input';
        return;
    }

    if (bar) bar.style.display = 'flex';

    if (state === 'listening') {
        if (micBtn) {
            micBtn.classList.add('mic-recording');
            micBtn.disabled = false;
        }
        if (micIcon) micIcon.textContent = '⏹️';
        if (micLabel) micLabel.textContent = 'Stop Listening';
        if (msgEl) {
            const lang = getSavedVoiceLanguage();
            const langLabel = (lang === 'ta-IN') ? 'தமிழ் (India)' : 'English (India)';
            msgEl.innerHTML = `<span style="color:#ff5c7c; animation: mic-pulse 1s infinite;">🔴</span> <strong style="color:#ff8da1;">Listening (${escapeHtml(langLabel)})...</strong> <span>Speak clearly into your microphone</span>`;
        }
        if (actionsEl) {
            actionsEl.innerHTML = `<button class="nexus-btn" style="padding:2px 8px; font-size:10px; background:#e53e3e; border-color:#fc8181;" onclick="stopSpeechRecognition()">⏹️ Stop Listening</button>`;
        }
    } else if (state === 'processing') {
        if (micBtn) {
            micBtn.classList.remove('mic-recording');
            micBtn.disabled = true;
        }
        if (micIcon) micIcon.textContent = '⏳';
        if (micLabel) micLabel.textContent = 'Transcribing';
        if (msgEl) {
            msgEl.innerHTML = `<span>⏳</span> <strong style="color:#f6ad55;">Processing speech...</strong>`;
        }
        if (actionsEl) actionsEl.innerHTML = '';
    } else if (state === 'success') {
        if (micBtn) {
            micBtn.classList.remove('mic-recording');
            micBtn.disabled = false;
        }
        if (micIcon) micIcon.textContent = '🎤';
        if (micLabel) micLabel.textContent = 'Voice Input';
        if (msgEl) {
            msgEl.innerHTML = `<span>✅</span> <strong style="color:#68d391;">Recognized:</strong> <span>${escapeHtml(message || 'Speech converted to text')}</span> <em style="color:#c4a5ff; font-size:10px;">(Review & click Send)</em>`;
        }
        if (actionsEl) {
            actionsEl.innerHTML = `<button class="nexus-btn" style="padding:2px 6px; font-size:10px;" onclick="setVoiceStatus('idle')">✕</button>`;
        }
        setTimeout(() => {
            const currentBar = document.getElementById('micStatusBar');
            if (currentBar && currentBar.style.display !== 'none' && !isRecordingAudio) {
                setVoiceStatus('idle');
            }
        }, 4000);
    } else if (state === 'error' || state === 'warning') {
        if (micBtn) {
            micBtn.classList.remove('mic-recording');
            micBtn.disabled = false;
        }
        if (micIcon) micIcon.textContent = '🎤';
        if (micLabel) micLabel.textContent = 'Voice Input';
        const color = state === 'error' ? '#ff5c7c' : '#f6ad55';
        if (msgEl) {
            msgEl.innerHTML = `<span style="color:${color};">⚠️</span> <span>${escapeHtml(message || 'Microphone error')}</span>`;
        }
        if (actionsEl) {
            actionsEl.innerHTML = `
                <div style="display:flex; gap:4px; align-items:center;">
                    ${showRetry ? '<button class="nexus-btn" style="padding:2px 8px; font-size:10px;" onclick="toggleSpeechRecognition()">🔄 Retry</button>' : ''}
                    <button class="nexus-btn" style="padding:2px 6px; font-size:10px;" onclick="setVoiceStatus('idle')">✕</button>
                </div>
            `;
        }
    }
}

function toggleVoiceInput() {
    toggleSpeechRecognition('assistantUserInput', 'voiceLangSelect', 'micBtn', 'micStatusBar');
}

function toggleSpeechRecognition(inputId = 'assistantUserInput', langSelectId = 'voiceLangSelect', micBtnId = 'micBtn', statusContainerId = 'micStatusBar') {
    // Guard against rapid duplicate clicks (STEP 4.1)
    if (isStartingSpeech) {
        return;
    }
    if (isRecordingAudio) {
        stopSpeechRecognition();
    } else {
        startSpeechRecognition(inputId, langSelectId, micBtnId, statusContainerId);
    }
}

function stopSpeechRecognition() {
    clearTimeout(voiceWatchdogTimer);
    isStartingSpeech = false;

    if (activeSpeechRecognition) {
        try {
            activeSpeechRecognition.abort();
        } catch (e) {
            console.warn("Speech recognition abort error:", e);
        }
        activeSpeechRecognition = null;
    }
    isRecordingAudio = false;

    // Reset desktop mic button if present
    const deskMicBtn = document.getElementById('desktopMicBtn');
    if (deskMicBtn) {
        deskMicBtn.classList.remove('mic-recording');
        const deskLabel = document.getElementById('desktopMicLabel');
        const deskIcon = document.getElementById('desktopMicIcon');
        if (deskLabel) deskLabel.textContent = 'Speak';
        if (deskIcon) deskIcon.textContent = '🎤';
    }
    const deskStatus = document.getElementById('desktopMicStatus');
    if (deskStatus) deskStatus.style.display = 'none';

    setVoiceStatus('idle');
}

// Backward-compatibility alias
function stopVoiceRecording(shouldTranscribe = false) {
    stopSpeechRecognition();
}

function startSpeechRecognition(inputId = 'assistantUserInput', langSelectId = 'voiceLangSelect', micBtnId = 'micBtn', statusContainerId = 'micStatusBar') {
    // 1. Check browser support before using API (STEP 3.1)
    const SpeechRecognitionClass = getSpeechRecognitionClass();
    if (!SpeechRecognitionClass) {
        const errorMsg = "Web Speech API is not supported in this browser. Please use Google Chrome, Microsoft Edge, or a Chromium-based browser with speech recognition enabled.";
        setVoiceStatus('error', errorMsg, false);
        const deskStatus = document.getElementById('desktopMicStatus');
        if (deskStatus) {
            deskStatus.style.display = 'block';
            deskStatus.innerHTML = `<span style="color:#ff5c7c;">⚠️ ${escapeHtml(errorMsg)}</span>`;
        }
        showToastNotification("⚠️ Web Speech API not supported in this browser.");
        return;
    }

    // Stop any existing active recognition instance safely
    if (activeSpeechRecognition || isRecordingAudio) {
        stopSpeechRecognition();
    }

    isStartingSpeech = true;
    clearTimeout(voiceWatchdogTimer);

    // 2. Language selection: en-IN (English India) or ta-IN (Tamil India) (STEP 3.6 & 3.7)
    let selectedLang = 'en-IN';
    const langSelectEl = document.getElementById(langSelectId);
    if (langSelectEl && langSelectEl.value) {
        selectedLang = langSelectEl.value;
        setSavedVoiceLanguage(selectedLang);
    } else {
        selectedLang = getSavedVoiceLanguage();
    }

    const langDisplayName = (selectedLang === 'ta-IN') ? 'தமிழ் (India)' : 'English (India)';

    // 3. Locate target input field and preserve any already typed user text (STEP 3.5 & STEP 4.5)
    const inputEl = document.getElementById(inputId) || document.getElementById('assistantUserInput') || document.getElementById('userInput');
    const existingText = inputEl ? inputEl.value : '';

    try {
        const recognition = new SpeechRecognitionClass();
        recognition.lang = selectedLang;
        recognition.continuous = false; // ONE-SHOT recognition per STEP 3.4
        recognition.interimResults = true; // Display recognized words in real time
        recognition.maxAlternatives = 1;

        let accumulatedTranscript = '';

        recognition.onstart = () => {
            isStartingSpeech = false;
            isRecordingAudio = true;
            activeSpeechRecognition = recognition;
            setVoiceStatus('listening');

            // 30-second safety watchdog so status never remains stuck (STEP 4.4)
            clearTimeout(voiceWatchdogTimer);
            voiceWatchdogTimer = setTimeout(() => {
                if (isRecordingAudio) {
                    stopSpeechRecognition();
                }
            }, 30000);

            // Handle desktop UI if targeted
            const deskMicBtn = document.getElementById('desktopMicBtn');
            if (deskMicBtn) {
                deskMicBtn.classList.add('mic-recording');
                const deskLabel = document.getElementById('desktopMicLabel');
                const deskIcon = document.getElementById('desktopMicIcon');
                if (deskLabel) deskLabel.textContent = 'Stop';
                if (deskIcon) deskIcon.textContent = '⏹️';
            }
            const deskStatus = document.getElementById('desktopMicStatus');
            if (deskStatus) {
                deskStatus.style.display = 'block';
                deskStatus.innerHTML = `<span style="color:#ff5c7c;">🔴</span> <strong>Listening (${escapeHtml(langDisplayName)})...</strong> <button class="nexus-btn" style="padding:1px 6px; font-size:10px; margin-left:6px;" onclick="stopSpeechRecognition()">Stop</button>`;
            }
        };

        recognition.onresult = (event) => {
            let interim = '';
            let final = '';

            for (let i = event.resultIndex; i < event.results.length; ++i) {
                const item = event.results[i];
                if (item.isFinal) {
                    final += item[0].transcript;
                } else {
                    interim += item[0].transcript;
                }
            }

            const currentSpoken = (final || interim).trim();
            if (currentSpoken) {
                accumulatedTranscript = currentSpoken;
                if (inputEl) {
                    const prefix = existingText ? (existingText.endsWith(' ') ? existingText : existingText + ' ') : '';
                    inputEl.value = prefix + currentSpoken;
                    inputEl.focus();
                }
            }
        };

        recognition.onerror = (event) => {
            console.warn("Speech recognition error:", event.error);
            clearTimeout(voiceWatchdogTimer);
            isStartingSpeech = false;
            isRecordingAudio = false;
            activeSpeechRecognition = null;

            // Preserve already typed user text if recognition produced no words
            if (!accumulatedTranscript && inputEl) {
                inputEl.value = existingText;
            }

            if (event.error === 'aborted') {
                setVoiceStatus('idle');
                const deskStatus = document.getElementById('desktopMicStatus');
                if (deskStatus) deskStatus.style.display = 'none';
                return;
            }

            let msg = 'Recognition error occurred.';
            let showRetry = true;

            if (event.error === 'not-allowed' || event.error === 'permission-denied') {
                msg = 'Microphone permission denied. Click the lock/tune icon in your browser address bar to allow microphone access.';
                showRetry = false;
            } else if (event.error === 'no-speech') {
                msg = 'No speech detected. Please speak clearly into your microphone.';
            } else if (event.error === 'audio-capture') {
                msg = 'No microphone device found or audio input is busy in another program.';
            } else if (event.error === 'network') {
                msg = 'Recognition service unavailable. Note: Browser speech recognition requires internet access to connect to browser speech services.';
            } else if (event.error === 'service-not-allowed') {
                msg = 'Browser speech recognition service is not allowed by policy or browser configuration.';
                showRetry = false;
            } else if (event.error === 'language-not-supported') {
                msg = `Selected language (${langDisplayName}) is not supported by your current browser.`;
            } else if (event.error === 'bad-grammar') {
                msg = 'Speech recognition grammar error occurred.';
            } else {
                msg = `Speech recognition error: ${event.error}`;
            }

            setVoiceStatus('error', msg, showRetry);
            showToastNotification(`⚠️ ${msg}`);

            const deskStatus = document.getElementById('desktopMicStatus');
            if (deskStatus) {
                deskStatus.style.display = 'block';
                deskStatus.innerHTML = `<span style="color:#ff5c7c;">⚠️ ${escapeHtml(msg)}</span>`;
            }

            const deskMicBtn = document.getElementById('desktopMicBtn');
            if (deskMicBtn) {
                deskMicBtn.classList.remove('mic-recording');
                const deskLabel = document.getElementById('desktopMicLabel');
                const deskIcon = document.getElementById('desktopMicIcon');
                if (deskLabel) deskLabel.textContent = 'Speak';
                if (deskIcon) deskIcon.textContent = '🎤';
            }
        };

        recognition.onend = () => {
            clearTimeout(voiceWatchdogTimer);
            isStartingSpeech = false;
            isRecordingAudio = false;
            activeSpeechRecognition = null;

            // Preserve existing text if no transcript was generated
            if (!accumulatedTranscript && inputEl) {
                inputEl.value = existingText;
            }

            const deskMicBtn = document.getElementById('desktopMicBtn');
            if (deskMicBtn) {
                deskMicBtn.classList.remove('mic-recording');
                const deskLabel = document.getElementById('desktopMicLabel');
                const deskIcon = document.getElementById('desktopMicIcon');
                if (deskLabel) deskLabel.textContent = 'Speak';
                if (deskIcon) deskIcon.textContent = '🎤';
            }

            if (accumulatedTranscript) {
                setVoiceStatus('success', `"${accumulatedTranscript.length > 30 ? accumulatedTranscript.slice(0, 30) + '...' : accumulatedTranscript}"`);
                const deskStatus = document.getElementById('desktopMicStatus');
                if (deskStatus) {
                    deskStatus.style.display = 'block';
                    deskStatus.innerHTML = `<span style="color:#68d391;">✅ Speech recognized.</span> <em>Review and click Send.</em>`;
                    setTimeout(() => {
                        if (deskStatus) deskStatus.style.display = 'none';
                    }, 4000);
                }
            } else {
                setVoiceStatus('idle');
                const deskStatus = document.getElementById('desktopMicStatus');
                if (deskStatus) deskStatus.style.display = 'none';
            }

            // CRITICAL STEP 3.9 & STEP 5:
            // Do NOT automatically send to Gemini. User reviews and edits, then clicks Send.
            if (inputEl) {
                inputEl.focus();
            }
        };

        // Start recognition - requests permission only when user clicks button (STEP 3.2 & 3.3)
        recognition.start();

    } catch (err) {
        console.error("Speech recognition startup error:", err);
        clearTimeout(voiceWatchdogTimer);
        isStartingSpeech = false;
        isRecordingAudio = false;
        activeSpeechRecognition = null;
        setVoiceStatus('error', `Failed to start speech recognition: ${err.message}`, true);
        showToastNotification(`⚠️ Failed to start speech recognition: ${err.message}`);
    }
}

// -----------------------------
// MARKDOWN & CODE BLOCKS
// -----------------------------

function renderMarkdownWithCodeBlocks(content) {
    if (typeof marked !== 'undefined') {
        marked.setOptions({ breaks: true, gfm: true });
    }
    const rawHtml = (typeof marked !== 'undefined') ? marked.parse(content) : escapeHtml(content);

    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = rawHtml;

    const preTags = tempDiv.querySelectorAll("pre");
    preTags.forEach(pre => {
        const codeTag = pre.querySelector("code");
        let lang = "code";
        if (codeTag && codeTag.className) {
            const match = codeTag.className.match(/language-([a-zA-Z0-9_-]+)/);
            if (match) lang = match[1];
        }

        const wrapper = document.createElement("div");
        wrapper.className = "code-block-wrapper";
        wrapper.innerHTML = `
            <div class="code-block-header">
                <span><strong>${lang.toUpperCase()}</strong></span>
                <button class="code-copy-btn" onclick="copySnippet(this)">📋 Copy Code</button>
            </div>
        `;
        pre.parentNode.insertBefore(wrapper, pre);
        wrapper.appendChild(pre);
    });

    return tempDiv.innerHTML;
}

function copySnippet(btn) {
    const wrapper = btn.closest(".code-block-wrapper");
    if (!wrapper) return;
    const preEl = wrapper.querySelector("pre");
    const text = preEl ? preEl.innerText : "";
    copyToClipboard(text, btn, "📋 Copy Code");
}

function copyChatMessage(text, btn) {
    copyToClipboard(text, btn, "📋 Copy");
}

function copyToClipboard(text, btn, originalLabel) {
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            if (btn) {
                btn.textContent = "✓ Copied!";
                btn.style.color = "#4ade80";
                setTimeout(() => {
                    btn.textContent = originalLabel;
                    btn.style.color = "";
                }, 2000);
            }
        }).catch(() => fallbackCopy(text, btn, originalLabel));
    } else {
        fallbackCopy(text, btn, originalLabel);
    }
}

function fallbackCopy(text, btn, originalLabel) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try {
        document.execCommand("copy");
        if (btn) {
            btn.textContent = "✓ Copied!";
            btn.style.color = "#4ade80";
            setTimeout(() => {
                btn.textContent = originalLabel;
                btn.style.color = "";
            }, 2000);
        }
    } catch(e) {
        showToastNotification("⚠️ Unable to copy to clipboard.");
    }
    document.body.removeChild(ta);
}

function formatAssistantMessage(content, timestamp) {
    const timeStr = timestamp ? new Date(timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    const rawContentAttr = encodeURIComponent(content);
    const renderedBody = renderMarkdownWithCodeBlocks(content);

    return `
        <div class="chat-message assistant-message" style="margin:8px 0; background:#2a1c40; padding:10px 14px; border-radius:8px; border-left:3px solid #a879e5; box-shadow:0 2px 8px rgba(0,0,0,0.2);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; border-bottom:1px solid rgba(168,121,229,0.15); padding-bottom:4px;">
                <strong style="color:#d8b4fe; display:flex; align-items:center; gap:6px;">
                    <span>🤖</span> NEXUS Assistant
                </strong>
                <div style="display:flex; align-items:center; gap:6px;">
                    <span style="font-size:11px; color:#a99ec2;">${timeStr}</span>
                    <button class="nexus-btn" style="padding:2px 6px; font-size:10px;" onclick="copyChatMessage(decodeURIComponent('${rawContentAttr}'), this)">📋 Copy</button>
                    <button class="nexus-btn" style="padding:2px 6px; font-size:10px;" onclick="speakText(decodeURIComponent('${rawContentAttr}'), this)">🔊 Listen</button>
                    <button class="nexus-btn" style="padding:2px 6px; font-size:10px;" onclick="regenerateResponse()">🔄 Regenerate</button>
                </div>
            </div>
            <div class="message-body" style="font-size:13px; line-height:1.6; color:#f3e8ff;">${renderedBody}</div>
        </div>
    `;
}

function formatUserMessage(content, timestamp) {
    const timeStr = timestamp ? new Date(timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    return `
        <div class="chat-message user-message" style="margin:8px 0; background:#362054; padding:10px 14px; border-radius:8px; border-left:3px solid #38bdf8; box-shadow:0 2px 8px rgba(0,0,0,0.15);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; border-bottom:1px solid rgba(56,189,248,0.15); padding-bottom:3px;">
                <strong style="color:#7dd3fc; display:flex; align-items:center; gap:6px;">
                    <span>👤</span> You
                </strong>
                <span style="font-size:11px; color:#a99ec2;">${timeStr}</span>
            </div>
            <div class="message-body" style="font-size:13px; line-height:1.5; color:#e0f2fe;">${escapeHtml(content)}</div>
        </div>
    `;
}

// -----------------------------
// DAY 8: PERSISTENT AI CHAT HISTORY
// -----------------------------

async function loadChatHistory(limit = 50) {
    const chatLog = document.getElementById('chatLog');
    if (!chatLog) return;

    // Show loading indicator while chat history is loading
    chatLog.innerHTML = `
        <div class="chat-empty-placeholder">
            <div class="typing-indicator" style="margin:20px auto;">
                <span></span><span></span><span></span>
                <em>Loading chat history...</em>
            </div>
        </div>
    `;

    try {
        const res = await safeFetchJson(`/api/chat/history?limit=${limit}`);
        chatLog.innerHTML = '';
        const messages = (res && Array.isArray(res.messages)) ? res.messages : [];

        if (messages.length === 0) {
            chatLog.innerHTML = `
                <div class="chat-empty-placeholder">
                    <p style="font-size:28px; margin-bottom:6px;">💬</p>
                    <p>No chat history yet. Say hello to NEXUS AI!</p>
                </div>
            `;
            return;
        }

        messages.forEach(m => {
            const role = m.role || 'user';
            const msg = m.message || '';
            const ts = m.created_at || '';
            const html = (role === 'user') 
                ? formatUserMessage(msg, ts) 
                : formatAssistantMessage(msg, ts);
            chatLog.insertAdjacentHTML('beforeend', html);
        });
        chatLog.scrollTop = chatLog.scrollHeight;
    } catch (err) {
        console.error("Failed to load chat history:", err);
        chatLog.innerHTML = `
            <div class="chat-empty-placeholder" style="color:#ff5c7c;">
                <p>⚠️ Failed to load chat history: ${escapeHtml(err.message)}</p>
                <button class="nexus-btn" onclick="loadChatHistory()">🔄 Retry</button>
            </div>
        `;
    }
}

// -----------------------------
// CONVERSATIONS & CHAT LOGIC
// -----------------------------

async function loadConversations(filterQuery = '') {
    const listEl = document.getElementById('conversationList');
    const badgeEl = document.getElementById('convCountBadge');
    const url = filterQuery ? `/api/conversations/search?q=${encodeURIComponent(filterQuery)}` : '/api/conversations';

    try {
        const data = await safeFetchJson(url);
        if (badgeEl) badgeEl.textContent = (data && data.length) ? data.length : 0;
        if (!listEl) return;

        listEl.innerHTML = '';

        if (!data || data.length === 0) {
            listEl.innerHTML = `
                <div class="conv-empty-state">
                    <div style="font-size:20px; margin-bottom:4px;">💬</div>
                    ${filterQuery ? 'No matching chats found.' : 'No chat history yet.<br/>Click <strong>➕ New Chat</strong> to start!'}
                </div>
            `;
            return;
        }

        data.forEach(conv => {
            const item = document.createElement('div');
            const isSelected = (conv.id === currentConversationId);
            item.className = `conv-item ${isSelected ? 'active' : ''}`;
            item.dataset.convId = conv.id;

            const nameText = conv.name || `Chat ${conv.id}`;
            const timeText = formatRelativeDate(conv.updated_at || conv.created_at);

            item.innerHTML = `
                <div style="flex:1; min-width:0;">
                    <div class="conv-item-title" title="${escapeHtml(nameText)}">💬 ${escapeHtml(nameText)}</div>
                    <div class="conv-item-time">${timeText}</div>
                </div>
                <div style="display:flex; gap:2px; align-items:center;" onclick="event.stopPropagation();">
                    <button class="conv-item-btn" title="Rename conversation" onclick="renameSpecificConversation(${conv.id}, '${escapeHtml(nameText).replace(/'/g, "\\'")}')">✏️</button>
                    <button class="conv-item-btn conv-item-del-btn" title="Delete conversation" onclick="deleteSpecificConversation(${conv.id}, '${escapeHtml(nameText).replace(/'/g, "\\'")}')">🗑️</button>
                </div>
            `;

            item.addEventListener('click', () => {
                switchConversation(conv.id, nameText);
            });

            listEl.appendChild(item);
        });

        // Mark active conversation in sidebar if selected
        if (currentConversationId && data.some(c => c.id === currentConversationId)) {
            const activeConv = data.find(c => c.id === currentConversationId);
            const titleEl = document.getElementById('activeChatTitle');
            if (titleEl && activeConv) titleEl.textContent = `💬 ${activeConv.name}`;
        }
    } catch (err) {
        console.error('Failed to load conversations:', err);
        if (listEl) {
            listEl.innerHTML = `<div class="conv-empty-state" style="color:#ff5c7c;">Failed to load conversations: ${escapeHtml(err.message)}</div>`;
        }
    }
}

async function switchConversation(convId, convName) {
    if (!convId) return;
    convId = parseInt(convId);
    setCurrentConversationId(convId);

    const listEl = document.getElementById('conversationList');
    if (listEl) {
        listEl.querySelectorAll('.conv-item').forEach(el => {
            if (parseInt(el.dataset.convId) === convId) {
                el.classList.add('active');
            } else {
                el.classList.remove('active');
            }
        });
    }

    const titleEl = document.getElementById('activeChatTitle');
    if (titleEl && convName) {
        titleEl.textContent = `💬 ${convName}`;
    }

    const chatLog = document.getElementById('chatLog');
    if (!chatLog) return;

    chatLog.innerHTML = `
        <div class="chat-empty-placeholder">
            <div class="typing-indicator" style="margin:20px auto;">
                <span></span><span></span><span></span>
                <em>Loading conversation...</em>
            </div>
        </div>
    `;

    try {
        const msgs = await safeFetchJson(`/api/conversations/${convId}/messages`);
        chatLog.innerHTML = '';
        if (!msgs || msgs.length === 0) {
            chatLog.innerHTML = `
                <div class="chat-empty-placeholder">
                    <p style="font-size:28px; margin-bottom:6px;">💬</p>
                    <p>No messages in this chat yet. Ask NEXUS AI anything!</p>
                </div>
            `;
            return;
        }

        msgs.forEach(m => {
            const html = m.role === 'user' ? formatUserMessage(m.content, m.timestamp) : formatAssistantMessage(m.content, m.timestamp);
            chatLog.insertAdjacentHTML('beforeend', html);
        });
        chatLog.scrollTop = chatLog.scrollHeight;
    } catch (err) {
        console.error("Switch conversation error:", err);
        chatLog.innerHTML = `
            <div class="chat-empty-placeholder" style="color:#ff5c7c;">
                <p>⚠️ Failed to load messages: ${escapeHtml(err.message)}</p>
                <button class="nexus-btn" onclick="switchConversation(${convId})">🔄 Retry</button>
            </div>
        `;
    }
}

async function renameSpecificConversation(convId, currentName) {
    if (!convId) return;
    const newName = prompt("Enter new title for this conversation:", currentName || `Chat #${convId}`);
    if (!newName || !newName.trim() || newName.trim() === currentName) return;

    try {
        const res = await safeFetchJson(`/api/conversations/${convId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName.trim() })
        });
        showToastNotification("✏️ Conversation renamed");
        loadConversations();
        if (currentConversationId === convId) {
            const titleEl = document.getElementById('activeChatTitle');
            if (titleEl) titleEl.textContent = `💬 ${res.name || newName.trim()}`;
        }
    } catch (err) {
        showToastNotification(`⚠️ Failed to rename: ${err.message}`);
    }
}

async function startNewConversation() {
    try {
        const conv = await safeFetchJson('/api/conversations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: "New Conversation" })
        });
        setCurrentConversationId(conv.id);
        const titleEl = document.getElementById('activeChatTitle');
        if (titleEl) titleEl.textContent = `💬 ${conv.name}`;

        const chatLog = document.getElementById('chatLog');
        if (chatLog) {
            chatLog.innerHTML = `
                <div class="chat-empty-placeholder">
                    <p style="font-size:28px; margin-bottom:6px;">✨</p>
                    <h4 style="margin:0 0 4px 0; color:#f3e8ff;">New Chat Session</h4>
                    <p style="margin:0; color:#a99ec2;">Type a message or use voice input to chat with NEXUS AI.</p>
                </div>
            `;
        }

        loadConversations();
        showToastNotification("✨ Started new chat session.");
        const input = document.getElementById("assistantUserInput");
        if (input) {
            input.value = "";
            input.focus();
        }
    } catch (err) {
        showToastNotification("⚠️ Failed to create chat: " + err.message);
    }
}

async function deleteSpecificConversation(convId, convName) {
    if (!convId) return;
    const nameStr = convName || `Chat #${convId}`;
    if (!confirm(`Are you sure you want to delete "${nameStr}"? This action cannot be undone.`)) {
        return;
    }

    try {
        await safeFetchJson(`/api/conversations/${convId}`, { method: 'DELETE' });
        if (currentConversationId === convId) {
            setCurrentConversationId(null);
            const titleEl = document.getElementById('activeChatTitle');
            if (titleEl) titleEl.textContent = "🤖 NEXUS AI Assistant";
            const chatLog = document.getElementById('chatLog');
            if (chatLog) {
                chatLog.innerHTML = `
                    <div class="chat-empty-placeholder">
                        <p style="font-size:26px; margin-bottom:6px;">✦</p>
                        <p>Conversation deleted. Start a new chat or select one from history.</p>
                    </div>
                `;
            }
        }
        loadConversations();
        showToastNotification("🗑️ Conversation deleted.");
    } catch (err) {
        showToastNotification("⚠️ Delete failed: " + err.message);
    }
}

function deleteCurrentConversation() {
    if (!currentConversationId) {
        showToastNotification("⚠️ No conversation selected to delete.");
        return;
    }
    const titleEl = document.getElementById('activeChatTitle');
    const name = titleEl ? titleEl.textContent.replace('💬 ', '') : null;
    deleteSpecificConversation(currentConversationId, name);
}

function clearChatUI() {
    const chatLog = document.getElementById('chatLog');
    if (chatLog) {
        chatLog.innerHTML = `
            <div class="chat-empty-placeholder">
                <p style="font-size:24px; margin-bottom:6px;">✦</p>
                <p>Chat cleared. Ask NEXUS AI anything.</p>
            </div>
        `;
    }
}

async function sendMessage() {
    if (isChatGenerating) return;

    const winInput = document.getElementById('assistantUserInput');
    const deskInput = document.getElementById('userInput');
    let input = (winInput && winInput.value.trim()) ? winInput : ((deskInput && deskInput.value.trim()) ? deskInput : (winInput || deskInput));

    const message = input ? input.value.trim() : '';
    if (!message) {
        showToastNotification("⚠️ Please enter a message first.");
        return;
    }

    const chatLog = document.getElementById('chatLog');
    if (chatLog) {
        const placeholder = chatLog.querySelector('.chat-empty-placeholder');
        if (placeholder) {
            placeholder.remove();
        }
        chatLog.insertAdjacentHTML('beforeend', formatUserMessage(message));
        chatLog.scrollTop = chatLog.scrollHeight;
    }
    input.value = '';

    const deskOutput = document.getElementById('output');
    if (deskOutput && !chatLog) {
        deskOutput.innerHTML = `<strong>You:</strong> ${escapeHtml(message)}<br/><em>AI is thinking...</em>`;
    }

    const loadingId = 'loadingMsg';
    if (chatLog) {
        chatLog.insertAdjacentHTML('beforeend', `
            <div id="${loadingId}" class="typing-indicator">
                <span></span><span></span><span></span>
                <em>NEXUS AI is thinking...</em>
            </div>
        `);
        chatLog.scrollTop = chatLog.scrollHeight;
    }

    setChatControlsDisabled(true);

    try {
        const data = await safeFetchJson('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, conversation_id: currentConversationId })
        });

        const loadEl = document.getElementById(loadingId);
        if (loadEl) loadEl.remove();

        const reply = data.reply;
        if (data.conversation_id) {
            setCurrentConversationId(data.conversation_id);
            loadConversations();
        }

        if (chatLog) {
            chatLog.insertAdjacentHTML('beforeend', formatAssistantMessage(reply, data.timestamp));
            chatLog.scrollTop = chatLog.scrollHeight;
        }
        if (deskOutput) {
            deskOutput.innerHTML = (typeof marked !== 'undefined') ? marked.parse(reply) : escapeHtml(reply);
        }

        if (voiceEnabled) speakText(reply);
        if (data.client_actions && data.client_actions.length > 0) {
            handleClientActions(data.client_actions);
        }
    } catch (err) {
        const loadEl = document.getElementById(loadingId);
        if (loadEl) loadEl.remove();

        if (chatLog) {
            const rawMsg = encodeURIComponent(message);
            chatLog.insertAdjacentHTML('beforeend', `
                <div style="color:#ff5c7c; padding:10px 14px; background:rgba(255,92,124,0.12); border-left:3px solid #ff5c7c; border-radius:6px; margin:8px 0; display:flex; justify-content:space-between; align-items:center; gap:8px;">
                    <div><strong>⚠️ Error:</strong> ${escapeHtml(err.message)}</div>
                    <button class="nexus-btn" style="padding:4px 8px; font-size:11px;" onclick="retryLastChatMessage(decodeURIComponent('${rawMsg}'))">🔄 Retry</button>
                </div>
            `);
            chatLog.scrollTop = chatLog.scrollHeight;
        }
        if (deskOutput) {
            deskOutput.innerHTML = `<span style="color:#ff5c7c;"><strong>Error:</strong> ${escapeHtml(err.message)}</span>`;
        }
    } finally {
        setChatControlsDisabled(false);
    }
}

async function regenerateResponse() {
    if (isChatGenerating || !currentConversationId) {
        showToastNotification("⚠️ No active conversation to regenerate.");
        return;
    }

    const chatLog = document.getElementById('chatLog');
    const loadingId = 'loadingMsg';
    if (chatLog) {
        const assistantMsgs = chatLog.querySelectorAll('.assistant-message');
        if (assistantMsgs.length > 0) {
            assistantMsgs[assistantMsgs.length - 1].remove();
        }
        chatLog.insertAdjacentHTML('beforeend', `
            <div id="${loadingId}" class="typing-indicator">
                <span></span><span></span><span></span>
                <em>NEXUS AI is regenerating response...</em>
            </div>
        `);
        chatLog.scrollTop = chatLog.scrollHeight;
    }

    setChatControlsDisabled(true);

    try {
        const data = await safeFetchJson('/api/chat/regenerate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ conversation_id: currentConversationId })
        });

        const loadEl = document.getElementById(loadingId);
        if (loadEl) loadEl.remove();

        const reply = data.reply;
        if (chatLog) {
            chatLog.insertAdjacentHTML('beforeend', formatAssistantMessage(reply, data.timestamp));
            chatLog.scrollTop = chatLog.scrollHeight;
        }
        if (voiceEnabled) speakText(reply);
        if (data.client_actions && data.client_actions.length > 0) {
            handleClientActions(data.client_actions);
        }
        showToastNotification("✨ Response regenerated.");
    } catch (err) {
        const loadEl = document.getElementById(loadingId);
        if (loadEl) loadEl.remove();
        if (chatLog) {
            chatLog.insertAdjacentHTML('beforeend', `
                <div style="color:#ff5c7c; padding:10px 14px; background:rgba(255,92,124,0.12); border-left:3px solid #ff5c7c; border-radius:6px; margin:8px 0; display:flex; justify-content:space-between; align-items:center; gap:8px;">
                    <div><strong>⚠️ Error:</strong> ${escapeHtml(err.message)}</div>
                    <button class="nexus-btn" style="padding:4px 8px; font-size:11px;" onclick="regenerateResponse()">🔄 Retry</button>
                </div>
            `);
            chatLog.scrollTop = chatLog.scrollHeight;
        }
    } finally {
        setChatControlsDisabled(false);
    }
}

function setChatControlsDisabled(disabled) {
    isChatGenerating = disabled;
    const sendBtn = document.getElementById("sendBtn");
    const micBtn = document.getElementById("micBtn");
    const inputEl = document.getElementById("assistantUserInput");
    if (sendBtn) sendBtn.disabled = disabled;
    if (micBtn) micBtn.disabled = disabled;
    if (inputEl) inputEl.disabled = disabled;
}

function retryLastChatMessage(message) {
    const input = document.getElementById('assistantUserInput') || document.getElementById('userInput');
    if (input) {
        input.value = message;
        sendMessage();
    }
}

// =================================
// TAB 2: REAL AI IMAGE STUDIO
// =================================

function renderImageStudio() {
    const container = document.getElementById("assistantImageView");
    if (!container) return;
    container.innerHTML = `
        <div class="image-studio-container">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h3 style="margin:0; font-size:16px; color:#f3e8ff; display:flex; align-items:center; gap:8px;">
                        <span>🎨</span> NEXUS AI Image Studio
                    </h3>
                    <p style="margin:2px 0 0 0; font-size:11px; color:#c4a5ff;">
                        Generate high-resolution visual art with Google Imagen 3 & Generative AI.
                    </p>
                </div>
                <button class="nexus-btn" onclick="loadImageStudioGallery()" style="padding:4px 10px; font-size:11px;">
                    🔄 Refresh Gallery
                </button>
            </div>

            <!-- Prompt Box & Parameters -->
            <div class="image-studio-prompt-box">
                <label style="font-size:11px; font-weight:600; color:#d8b4fe; text-transform:uppercase; letter-spacing:0.5px;">
                    Describe what you want to create:
                </label>
                <textarea id="imageStudioPrompt" class="nexus-input" placeholder="e.g. A hyper-realistic cyberpunk city at twilight with glowing purple neon signs and flying vehicles in 8k resolution..." style="width:100%; height:72px; resize:vertical; font-size:12px; box-sizing:border-box;"></textarea>
                
                <!-- Quick Inspiration Chips -->
                <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
                    <span style="font-size:10px; color:#9d8bb8; font-weight:600;">Inspiration:</span>
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px; border-radius:12px;" onclick="setImageStudioPrompt('A hyper-realistic cyberpunk metropolis at twilight with glowing purple neon reflections, volumetric rain, 8k cinematic')">🌆 Cyberpunk</button>
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px; border-radius:12px;" onclick="setImageStudioPrompt('Glowing futuristic AI holographic brain core floating inside a dark violet crystalline server room, photorealistic')">🧠 AI Core</button>
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px; border-radius:12px;" onclick="setImageStudioPrompt('Deep space nebula swirling in vibrant purple and magenta cosmic dust with distant radiant stars, NASA astronomy photo style')">🌌 Nebula</button>
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px; border-radius:12px;" onclick="setImageStudioPrompt('Cozy isometric developer workspace at night with multi-monitor glowing setup, mechanical keyboard, and potted plants, 3D render')">💻 Isometric Desk</button>
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px; border-radius:12px;" onclick="setImageStudioPrompt('Minimalist glowing purple geometric logo for a next-gen operating system on dark matte texture')">✨ Minimalist Logo</button>
                </div>

                <!-- Aspect Ratio & Generate Button -->
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-top:4px;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <label style="font-size:11px; color:#b9a6d5;">Aspect Ratio:</label>
                        <select id="imageStudioRatio" class="nexus-input" style="padding:4px 8px; font-size:11px;">
                            <option value="1:1" selected>1:1 (Square)</option>
                            <option value="16:9">16:9 (Landscape)</option>
                            <option value="9:16">9:16 (Portrait)</option>
                            <option value="4:3">4:3 (Standard)</option>
                        </select>
                    </div>
                    <button id="imageStudioGenBtn" class="nexus-btn" style="padding:7px 18px; font-size:12px; font-weight:600; background:linear-gradient(135deg, #7c3aed, #a855f7); border-color:#c084fc;" onclick="generateImageStudioArtwork()">
                        ✨ Generate Artwork
                    </button>
                </div>

                <!-- Generation Progress Indicator -->
                <div id="imageStudioProgress" style="display:none; align-items:center; gap:8px; padding:10px; background:#26183c; border-radius:6px; border:1px solid #7c3aed;">
                    <div class="typing-indicator" style="margin:0;">
                        <span></span><span></span><span></span>
                    </div>
                    <span id="imageStudioProgressText" style="font-size:12px; color:#f3e8ff;">Generating artwork with AI...</span>
                </div>
            </div>

            <!-- Active Generated Image Area -->
            <div id="imageStudioActiveArea" style="display:none; background:#191228; border:1px solid #7c3aed; border-radius:10px; padding:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <h4 style="margin:0; font-size:13px; color:#f3e8ff;" id="activeImageTitle">✨ Newly Generated Artwork</h4>
                    <div style="display:flex; gap:6px;">
                        <button id="downloadActiveImgBtn" class="nexus-btn" style="padding:4px 10px; font-size:11px;">⬇️ Download Image</button>
                        <button id="regenerateActiveImgBtn" class="nexus-btn" style="padding:4px 10px; font-size:11px;">🔄 Generate Again</button>
                    </div>
                </div>
                <div style="display:flex; flex-direction:column; align-items:center; gap:10px;">
                    <img id="activeImageDisplay" src="" alt="AI Generated Image" style="max-width:100%; max-height:360px; object-fit:contain; border-radius:8px; border:1px solid #3d2b59; background:#0f0a18;" />
                    <div id="activeImagePrompt" style="font-size:12px; color:#d8b4fe; text-align:center; max-width:85%;"></div>
                    <div id="activeImageMeta" style="font-size:10px; color:#9d8bb8;"></div>
                </div>
            </div>

            <!-- Recent Creations Gallery -->
            <div>
                <h4 style="margin:10px 0 6px 0; font-size:13px; color:#e2d9f3; display:flex; justify-content:space-between; align-items:center;">
                    <span>🖼️ Recent Creations Gallery</span>
                    <span id="galleryCountBadge" style="font-size:10px; color:#c4a5ff; background:rgba(168,121,229,0.15); padding:1px 6px; border-radius:10px;">0 images</span>
                </h4>
                <div id="imageGalleryGrid" class="image-gallery-grid">
                    <div style="grid-column: 1/-1; text-align:center; padding:30px; color:#8e7da8; font-size:12px;">
                        Loading generated images...
                    </div>
                </div>
            </div>
        </div>
    `;
    loadImageStudioGallery();
}

function setImageStudioPrompt(prompt) {
    const p = document.getElementById("imageStudioPrompt");
    if (p) {
        p.value = prompt;
        p.focus();
    }
}

async function generateImageStudioArtwork() {
    const promptInput = document.getElementById("imageStudioPrompt");
    const ratioInput = document.getElementById("imageStudioRatio");
    const genBtn = document.getElementById("imageStudioGenBtn");
    const progress = document.getElementById("imageStudioProgress");
    const progressText = document.getElementById("imageStudioProgressText");

    const prompt = (promptInput?.value || "").trim();
    if (!prompt) {
        showToastNotification("⚠️ Please enter a description for the image.");
        return;
    }
    const aspectRatio = ratioInput?.value || "1:1";

    if (genBtn) genBtn.disabled = true;
    if (progress) progress.style.display = "flex";
    if (progressText) progressText.textContent = `Generating "${prompt.slice(0, 30)}..." with AI...`;

    try {
        const res = await safeFetchJson('/api/images/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt, aspect_ratio: aspectRatio })
        });

        if (res.image) {
            displayActiveGeneratedImage(res.image);
            showToastNotification("🎨 Image generated successfully!");
            loadImageStudioGallery();
        }
    } catch (err) {
        showToastNotification(`⚠️ Image generation failed: ${err.message}`);
    } finally {
        if (genBtn) genBtn.disabled = false;
        if (progress) progress.style.display = "none";
    }
}

function displayActiveGeneratedImage(img) {
    currentGeneratedImage = img;
    const activeArea = document.getElementById("imageStudioActiveArea");
    const displayImg = document.getElementById("activeImageDisplay");
    const promptEl = document.getElementById("activeImagePrompt");
    const metaEl = document.getElementById("activeImageMeta");
    const dlBtn = document.getElementById("downloadActiveImgBtn");
    const regenBtn = document.getElementById("regenerateActiveImgBtn");

    if (!activeArea || !displayImg) return;
    activeArea.style.display = "block";
    displayImg.src = img.url;
    if (promptEl) promptEl.textContent = `"${img.prompt}"`;
    if (metaEl) metaEl.textContent = `Aspect Ratio: ${img.aspect_ratio || '1:1'} • Model: ${img.model || 'AI'} • Created: ${new Date(img.created_at).toLocaleTimeString()}`;

    if (dlBtn) {
        dlBtn.onclick = () => downloadImageFile(img.url, img.filename || 'nexus-ai-artwork.jpg');
    }
    if (regenBtn) {
        regenBtn.onclick = () => {
            const p = document.getElementById("imageStudioPrompt");
            if (p) p.value = img.prompt;
            generateImageStudioArtwork();
        };
    }
    activeArea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function downloadImageFile(url, filename) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'nexus-ai-image.jpg';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToastNotification("⬇️ Downloading image...");
}

async function deleteImageStudioArtwork(id) {
    if (!confirm("Are you sure you want to delete this generated image?")) return;
    try {
        await safeFetchJson(`/api/images/${id}`, { method: 'DELETE' });
        showToastNotification("🗑️ Image deleted.");
        loadImageStudioGallery();
        const activeArea = document.getElementById("imageStudioActiveArea");
        if (currentGeneratedImage && currentGeneratedImage.id === id && activeArea) {
            activeArea.style.display = "none";
            currentGeneratedImage = null;
        }
    } catch (err) {
        showToastNotification(`⚠️ Failed to delete image: ${err.message}`);
    }
}

async function loadImageStudioGallery() {
    const grid = document.getElementById("imageGalleryGrid");
    const countBadge = document.getElementById("galleryCountBadge");
    if (!grid) return;

    try {
        const images = await safeFetchJson('/api/images');
        if (countBadge) countBadge.textContent = `${images.length} image${images.length === 1 ? '' : 's'}`;

        if (!images || images.length === 0) {
            grid.innerHTML = `
                <div style="grid-column:1/-1; text-align:center; padding:30px; color:#8e7da8; font-size:12px;">
                    <div style="font-size:24px; margin-bottom:6px;">🎨</div>
                    No images generated yet. Describe an image above and click <strong>Generate Artwork</strong>!
                </div>
            `;
            return;
        }

        grid.innerHTML = images.map(img => `
            <div class="image-card" data-img-id="${img.id}">
                <img src="${img.url}" alt="${escapeHtml(img.prompt)}" loading="lazy" onclick="displayActiveGeneratedImage(${escapeJsonAttr(img)})" title="Click to view full preview" />
                <div class="image-card-body">
                    <div class="image-card-prompt" title="${escapeHtml(img.prompt)}">${escapeHtml(img.prompt)}</div>
                    <div class="image-card-meta">
                        <span>📐 ${img.aspect_ratio || '1:1'}</span>
                        <div style="display:flex; gap:4px;">
                            <button class="nexus-btn" style="padding:2px 6px; font-size:10px;" onclick="downloadImageFile('${img.url}', '${escapeHtml(img.filename)}')">⬇️</button>
                            <button class="nexus-btn nexus-btn-danger" style="padding:2px 6px; font-size:10px;" onclick="deleteImageStudioArtwork(${img.id})">🗑️</button>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (err) {
        grid.innerHTML = `<div style="grid-column:1/-1; text-align:center; padding:20px; color:#ff5c7c; font-size:12px;">Failed to load gallery: ${escapeHtml(err.message)}</div>`;
    }
}

// =================================
// TAB 3: FILE INTELLIGENCE IN ASSISTANT
// =================================

function renderAssistantFilesView() {
    const container = document.getElementById("assistantFilesView");
    if (!container) return;
    container.innerHTML = `
        <div style="padding:10px; display:flex; flex-direction:column; gap:10px; height:480px; overflow-y:auto;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h3 style="margin:0; font-size:16px; color:#f3e8ff; display:flex; align-items:center; gap:8px;">
                        <span>📁</span> File Intelligence & Document Analysis
                    </h3>
                    <p style="margin:2px 0 0 0; font-size:11px; color:#c4a5ff;">Upload and interrogate documents (PDF, DOCX, TXT, CSV, JSON, MD, PY, JS) using Gemini AI.</p>
                </div>
                <button class="nexus-btn" onclick="openApp('File Manager')" style="padding:4px 10px; font-size:11px;">
                    📂 Full File Manager
                </button>
            </div>

            <!-- Upload Card -->
            <div style="background:#191228; padding:12px; border-radius:8px; border:1px solid #3d2b59;">
                <label style="font-size:11px; font-weight:bold; display:block; margin-bottom:6px; color:#d8b4fe;">Upload & Analyze Document:</label>
                <div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center;">
                    <input type="file" id="asstFilePicker" style="font-size:12px; flex:1; min-width:200px;">
                    <button id="asstUploadFileBtn" class="nexus-btn" style="padding:5px 12px; background:#68449b;" onclick="uploadAssistantFile()">⬆ Upload & Ingest</button>
                    <span id="asstUploadStatus" style="font-size:12px; color:#c4a5ff;"></span>
                </div>
            </div>

            <!-- Search and Filter -->
            <div style="display:flex; gap:8px; align-items:center;">
                <input type="text" id="asstFileSearch" class="nexus-input" placeholder="🔍 Search documents..." style="flex:1; font-size:11px;" />
                <button class="nexus-btn" style="padding:4px 10px; font-size:11px;" onclick="loadAssistantFiles()">🔄 Refresh</button>
            </div>

            <!-- Files List -->
            <h4 style="margin:4px 0; font-size:12px; color:#e2d9f3;">Stored Documents</h4>
            <div id="asstFileList" style="max-height:160px; overflow-y:auto; padding-right:4px;">
                <div style="text-align:center; padding:15px; color:#8e7da8; font-size:11px;">Loading files...</div>
            </div>

            <!-- Ask AI & Document Analysis Box -->
            <div id="asstFileWorkspace" style="display:none; background:#191228; border:1px solid #7c3aed; border-radius:8px; padding:12px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; border-bottom:1px solid #3d2b59; padding-bottom:6px;">
                    <span id="asstActiveFileTitle" style="font-weight:bold; color:#d8b4fe; font-size:12px;">Selected Document</span>
                    <button onclick="document.getElementById('asstFileWorkspace').style.display='none'" class="nexus-btn nexus-btn-danger" style="padding:2px 6px; font-size:10px;">✕</button>
                </div>
                <div style="display:flex; gap:6px; margin-bottom:8px;">
                    <input type="text" id="asstFileQuestionInput" class="nexus-input" placeholder="Ask Gemini anything about this document..." style="flex:1; font-size:12px;" />
                    <button id="asstAskFileBtn" class="nexus-btn" style="padding:4px 12px; font-size:12px; background:#68449b;" onclick="askAssistantFileQuestion()">Ask AI</button>
                </div>
                <div id="asstFileAnswerBox" style="background:#120c1e; border:1px solid #3d2b59; border-radius:6px; padding:10px; min-height:60px; max-height:160px; overflow:auto; font-size:12px; line-height:1.5; color:#f3e8ff;">
                    <em>Select a document and ask a question to interrogate its content.</em>
                </div>
            </div>
        </div>
    `;

    const searchInput = document.getElementById("asstFileSearch");
    if (searchInput) {
        let debounceTimer;
        searchInput.addEventListener("input", e => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                loadAssistantFiles(e.target.value.trim());
            }, 250);
        });
    }

    const qInput = document.getElementById("asstFileQuestionInput");
    if (qInput) {
        qInput.addEventListener("keydown", e => {
            if (e.key === "Enter") askAssistantFileQuestion();
        });
    }

    loadAssistantFiles();
}

async function loadAssistantFiles(query = '') {
    const list = document.getElementById("asstFileList");
    if (!list) return;
    const url = query ? `/api/files/uploaded-search?q=${encodeURIComponent(query)}` : '/api/files';
    try {
        const files = await safeFetchJson(url);
        if (!files || files.length === 0) {
            list.innerHTML = `<div style="text-align:center; padding:15px; color:#8e7da8; font-size:11px;">No documents found. Upload a file above!</div>`;
            return;
        }

        list.innerHTML = files.map(f => `
            <div style="background:#26183c; border:1px solid #3d2b59; border-radius:6px; padding:8px 10px; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center;">
                <div style="min-width:0; flex:1;">
                    <div style="font-weight:600; font-size:12px; color:#f3e8ff; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">📄 ${escapeHtml(f.filename)}</div>
                    <div style="font-size:10px; color:#9d8bb8;">${f.category || 'File'} • ${(f.size / 1024).toFixed(1)} KB</div>
                </div>
                <div style="display:flex; gap:4px; margin-left:8px;">
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px; background:#68449b;" onclick="selectAssistantFile(${f.id}, '${escapeHtml(f.filename).replace(/'/g, "\\'")}')">🤖 Interrogate</button>
                    <button class="nexus-btn nexus-btn-danger" style="padding:2px 6px; font-size:10px;" onclick="deleteAssistantFile(${f.id})">🗑️</button>
                </div>
            </div>
        `).join('');
    } catch (err) {
        list.innerHTML = `<div style="color:#ff5c7c; font-size:11px; padding:10px;">Failed to load files: ${escapeHtml(err.message)}</div>`;
    }
}

async function uploadAssistantFile() {
    const picker = document.getElementById("asstFilePicker");
    const status = document.getElementById("asstUploadStatus");
    const btn = document.getElementById("asstUploadFileBtn");
    if (!picker || !picker.files || picker.files.length === 0) {
        showToastNotification("⚠️ Please select a file first.");
        return;
    }
    const file = picker.files[0];
    const formData = new FormData();
    formData.append("file", file);

    if (btn) btn.disabled = true;
    if (status) status.textContent = "Uploading & extracting...";

    try {
        const res = await safeFetchJson('/api/files/upload', {
            method: 'POST',
            body: formData
        });
        showToastNotification(`✅ Ingested "${file.name}" with AI analysis!`);
        picker.value = "";
        if (status) status.textContent = "";
        loadAssistantFiles();
        if (res.file && res.file.id) {
            selectAssistantFile(res.file.id, res.file.filename);
        }
    } catch (err) {
        showToastNotification(`⚠️ Upload failed: ${err.message}`);
        if (status) status.textContent = "Upload failed.";
    } finally {
        if (btn) btn.disabled = false;
    }
}

function selectAssistantFile(fileId, filename) {
    asstActiveFileId = fileId;
    const ws = document.getElementById("asstFileWorkspace");
    const title = document.getElementById("asstActiveFileTitle");
    const answerBox = document.getElementById("asstFileAnswerBox");
    const input = document.getElementById("asstFileQuestionInput");

    if (ws) ws.style.display = "block";
    if (title) title.textContent = `📄 ${filename}`;
    if (answerBox) answerBox.innerHTML = `<em>Ready to interrogate <strong>${escapeHtml(filename)}</strong>. Type a question above!</em>`;
    if (input) {
        input.value = "";
        input.focus();
    }
    ws?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function askAssistantFileQuestion() {
    if (!asstActiveFileId) {
        showToastNotification("⚠️ Please select a file first.");
        return;
    }
    const input = document.getElementById("asstFileQuestionInput");
    const btn = document.getElementById("asstAskFileBtn");
    const answerBox = document.getElementById("asstFileAnswerBox");
    const question = (input?.value || "").trim();
    if (!question) {
        showToastNotification("⚠️ Please enter a question.");
        return;
    }

    if (btn) btn.disabled = true;
    if (answerBox) {
        answerBox.innerHTML = `
            <div class="typing-indicator" style="margin:10px 0;">
                <span></span><span></span><span></span>
                <em>Analyzing document and generating answer...</em>
            </div>
        `;
    }

    try {
        const res = await safeFetchJson(`/api/files/${asstActiveFileId}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question })
        });

        const replyHtml = (typeof marked !== 'undefined') ? marked.parse(res.answer || '') : escapeHtml(res.answer || '');
        if (answerBox) answerBox.innerHTML = replyHtml;
    } catch (err) {
        if (answerBox) answerBox.innerHTML = `<span style="color:#ff5c7c;">⚠️ Error: ${escapeHtml(err.message)}</span>`;
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function deleteAssistantFile(id) {
    if (!confirm("Are you sure you want to delete this document?")) return;
    try {
        await safeFetchJson(`/api/files/${id}`, { method: 'DELETE' });
        showToastNotification("🗑️ File deleted.");
        loadAssistantFiles();
        if (asstActiveFileId === id) {
            const ws = document.getElementById("asstFileWorkspace");
            if (ws) ws.style.display = "none";
            asstActiveFileId = null;
        }
    } catch (err) {
        showToastNotification(`⚠️ Failed to delete: ${err.message}`);
    }
}

// =================================
// TAB 4: CONVERSATION HISTORY MANAGER
// =================================

async function renderAssistantHistoryView() {
    const container = document.getElementById("assistantHistoryView");
    if (!container) return;
    container.innerHTML = `
        <div style="padding:10px; display:flex; flex-direction:column; gap:12px; height:480px; overflow-y:auto;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h3 style="margin:0; font-size:16px; color:#f3e8ff;">🕒 Conversation History Manager</h3>
                    <p style="margin:2px 0 0 0; font-size:11px; color:#c4a5ff;">Manage and review past AI chat conversations stored in SQLite.</p>
                </div>
                <button class="nexus-btn" onclick="startNewConversation(); switchAssistantTab('chat');" style="padding:5px 12px; font-size:11px; background:#68449b;">
                    ➕ New Chat
                </button>
            </div>
            <div>
                <input type="text" id="historyViewSearchInput" class="nexus-input" placeholder="🔍 Search through past conversations..." style="width:100%; box-sizing:border-box; font-size:12px;" />
            </div>
            <div id="historyTableContainer" style="background:#191228; border:1px solid #3d2b59; border-radius:8px; overflow:hidden;">
                <div style="text-align:center; padding:30px; color:#8e7da8; font-size:12px;">Loading conversation history...</div>
            </div>
        </div>
    `;

    const searchInput = document.getElementById("historyViewSearchInput");
    if (searchInput) {
        let debounceTimer;
        searchInput.addEventListener("input", e => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                loadHistoryTableData(e.target.value.trim());
            }, 250);
        });
    }

    loadHistoryTableData();
}

async function loadHistoryTableData(query = '') {
    const container = document.getElementById("historyTableContainer");
    if (!container) return;
    const url = query ? `/api/conversations/search?q=${encodeURIComponent(query)}` : '/api/conversations';
    try {
        const convs = await safeFetchJson(url);
        if (!convs || convs.length === 0) {
            container.innerHTML = `
                <div style="text-align:center; padding:35px; color:#8e7da8; font-size:12px;">
                    <div style="font-size:24px; margin-bottom:6px;">💬</div>
                    ${query ? 'No matching conversations found.' : 'No conversations recorded yet. Start chatting in the AI Chat tab!'}
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <table style="width:100%; border-collapse:collapse; font-size:12px; text-align:left;">
                <thead>
                    <tr style="background:#26183c; border-bottom:1px solid #3d2b59; color:#d8b4fe;">
                        <th style="padding:10px 12px;">ID</th>
                        <th style="padding:10px 12px;">Title</th>
                        <th style="padding:10px 12px;">Last Updated</th>
                        <th style="padding:10px 12px; text-align:right;">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${convs.map(c => `
                        <tr style="border-bottom:1px solid rgba(168,121,229,0.1); transition:background 0.2s;" onmouseover="this.style.background='rgba(168,121,229,0.06)'" onmouseout="this.style.background='transparent'">
                            <td style="padding:10px 12px; color:#9d8bb8; font-family:monospace;">#${c.id}</td>
                            <td style="padding:10px 12px; font-weight:600; color:#f3e8ff;">${escapeHtml(c.name || 'Conversation ' + c.id)}</td>
                            <td style="padding:10px 12px; color:#a99ec2;">${formatRelativeDate(c.updated_at || c.created_at)}</td>
                            <td style="padding:10px 12px; text-align:right;">
                                <button class="nexus-btn" style="padding:3px 8px; font-size:11px; margin-right:4px;" onclick="switchConversation(${c.id}, '${escapeHtml(c.name || '').replace(/'/g, "\\'")}'); switchAssistantTab('chat');">💬 Open</button>
                                <button class="nexus-btn" style="padding:3px 8px; font-size:11px; margin-right:4px;" onclick="renameSpecificConversation(${c.id}, '${escapeHtml(c.name || '').replace(/'/g, "\\'")}').then(() => loadHistoryTableData())">✏️ Rename</button>
                                <button class="nexus-btn nexus-btn-danger" style="padding:3px 8px; font-size:11px;" onclick="deleteSpecificConversation(${c.id}, '${escapeHtml(c.name || '').replace(/'/g, "\\'")}'); setTimeout(() => loadHistoryTableData(), 300);">🗑️ Delete</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (err) {
        container.innerHTML = `<div style="text-align:center; padding:20px; color:#ff5c7c; font-size:12px;">Error loading history: ${escapeHtml(err.message)}</div>`;
    }
}

// =================================
// TAB 5: AI AGENT DESKTOP CONSOLE
// =================================

function renderAssistantAgentView() {
    const container = document.getElementById("assistantAgentView");
    if (!container) return;
    container.innerHTML = `
        <div style="padding:10px; display:flex; flex-direction:column; gap:12px; height:480px; overflow-y:auto;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h3 style="margin:0; font-size:16px; color:#f3e8ff; display:flex; align-items:center; gap:8px;">
                        <span>⚡</span> AI Desktop Agent & Automation
                    </h3>
                    <p style="margin:2px 0 0 0; font-size:11px; color:#c4a5ff;">Autonomous multi-step planning and tool execution across NEXUS OS.</p>
                </div>
                <button class="nexus-btn" onclick="openApp('AI Agent Dashboard')" style="padding:4px 10px; font-size:11px;">
                    🚀 Full Dashboard
                </button>
            </div>

            <!-- Command input bar -->
            <div style="background:#191228; border:1px solid #3d2b59; border-radius:10px; padding:12px; display:flex; flex-direction:column; gap:8px;">
                <label style="font-size:11px; font-weight:600; color:#d8b4fe; text-transform:uppercase;">Agent Command:</label>
                <div style="display:flex; gap:8px;">
                    <input type="text" id="assistantAgentCommandInput" class="nexus-input" placeholder="e.g. Create a high priority task to review deployment logs tomorrow" style="flex:1; font-size:12px;" />
                    <button id="runAssistantAgentBtn" class="nexus-btn" style="padding:6px 16px; font-size:12px; font-weight:600; background:#68449b; border-color:#a879e5;" onclick="executeAssistantAgentCommand()">
                        ⚡ Run Agent
                    </button>
                </div>
                <!-- Quick sample prompts -->
                <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center; margin-top:2px;">
                    <span style="font-size:10px; color:#9d8bb8; font-weight:600;">Quick Actions:</span>
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px; border-radius:12px;" onclick="setAgentCommand('Create a note about today\'s AI development sprint')">📝 Note</button>
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px; border-radius:12px;" onclick="setAgentCommand('Add a high-priority task: Deploy NEXUS AI OS on desktop')">📋 Task</button>
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px; border-radius:12px;" onclick="setAgentCommand('Schedule event: Architecture Review Tomorrow at 10 AM')">📅 Event</button>
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px; border-radius:12px;" onclick="setAgentCommand('Generate an image of a cyberpunk city at night')">🎨 Image</button>
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px; border-radius:12px;" onclick="setAgentCommand('Check system resource statistics and status')">💻 System</button>
                </div>
            </div>

            <!-- Execution Status & Results -->
            <div id="assistantAgentResults" style="display:none; background:#191228; border:1px solid #4a336e; border-radius:8px; padding:12px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; border-bottom:1px solid #3d2b59; padding-bottom:6px;">
                    <strong style="color:#d8b4fe; font-size:12px;">Agent Execution Trace</strong>
                    <span id="assistantAgentStatusBadge" style="font-size:10px; padding:2px 6px; border-radius:10px; background:rgba(104,211,145,0.2); color:#68d391;">SUCCESS</span>
                </div>
                <div id="assistantAgentResultBody" style="font-size:12px; line-height:1.6; color:#f3e8ff;"></div>
            </div>
        </div>
    `;

    const input = document.getElementById("assistantAgentCommandInput");
    if (input) {
        input.addEventListener("keydown", e => {
            if (e.key === "Enter") {
                executeAssistantAgentCommand();
            }
        });
    }
}

function setAgentCommand(cmd) {
    const input = document.getElementById("assistantAgentCommandInput");
    if (input) {
        input.value = cmd;
        input.focus();
    }
}

async function executeAssistantAgentCommand() {
    const input = document.getElementById("assistantAgentCommandInput");
    const runBtn = document.getElementById("runAssistantAgentBtn");
    const resultsBox = document.getElementById("assistantAgentResults");
    const statusBadge = document.getElementById("assistantAgentStatusBadge");
    const resultBody = document.getElementById("assistantAgentResultBody");

    const command = (input?.value || "").trim();
    if (!command) {
        showToastNotification("⚠️ Please enter an agent command first.");
        return;
    }

    if (runBtn) runBtn.disabled = true;
    if (resultsBox) resultsBox.style.display = "block";
    if (statusBadge) {
        statusBadge.textContent = "RUNNING";
        statusBadge.style.background = "rgba(246,173,85,0.2)";
        statusBadge.style.color = "#f6ad55";
    }
    if (resultBody) {
        resultBody.innerHTML = `
            <div class="typing-indicator" style="margin:10px 0;">
                <span></span><span></span><span></span>
                <em>Agent is planning and executing tools...</em>
            </div>
        `;
    }

    try {
        const res = await safeFetchJson('/api/agent/command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command })
        });

        if (statusBadge) {
            statusBadge.textContent = (res.status || 'DONE').toUpperCase();
            statusBadge.style.background = "rgba(104,211,145,0.2)";
            statusBadge.style.color = "#68d391";
        }

        const replyHtml = (typeof marked !== 'undefined') ? marked.parse(res.reply || 'Command completed.') : escapeHtml(res.reply || 'Command completed.');
        let toolsHtml = '';
        if (res.tools_called && res.tools_called.length > 0) {
            toolsHtml = `
                <div style="margin-top:8px; padding-top:8px; border-top:1px solid #3d2b59; font-size:11px; color:#c4a5ff;">
                    <strong>Tools Executed:</strong> ${res.tools_called.join(', ')}
                </div>
            `;
        }
        if (resultBody) {
            resultBody.innerHTML = replyHtml + toolsHtml;
        }

        if (res.client_actions && res.client_actions.length > 0) {
            handleClientActions(res.client_actions);
        }

        showToastNotification("⚡ Agent execution finished.");
    } catch (err) {
        if (statusBadge) {
            statusBadge.textContent = "ERROR";
            statusBadge.style.background = "rgba(255,92,124,0.2)";
            statusBadge.style.color = "#ff5c7c";
        }
        if (resultBody) {
            resultBody.innerHTML = `<span style="color:#ff5c7c;"><strong>Error:</strong> ${escapeHtml(err.message)}</span>`;
        }
    } finally {
        if (runBtn) runBtn.disabled = false;
    }
}


// =================================
// NOTES APPLICATION (Backend‑persistent with Search)
// =================================

let allNotes = [];

function showNotes() {
    const content = document.getElementById("windowContent");
    content.innerHTML = `
        <h3>📝 My Notes</h3>
        <p style="color:#b9a6d5; font-size:12px; margin-bottom:12px;">Persistent Notes with live SQLite storage.</p>
        
        <div style="background:#191228; padding:12px; border-radius:8px; margin-bottom:12px; border:1px solid #3d2b59;">
            <textarea id="newNoteText" class="nexus-input" placeholder="Write a new note..." style="width:100%; height:75px; resize:vertical; margin-bottom:8px;"></textarea>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <button id="addNoteBtn" class="nexus-btn">💾 Add Note</button>
                <span id="notesStatus" style="font-size:12px; color:#ff5c7c;"></span>
            </div>
        </div>

        <div style="margin-bottom:12px;">
            <input type="text" id="noteSearchInput" class="nexus-input" placeholder="🔍 Search notes..." style="width:100%;">
        </div>

        <div id="notesList" style="max-height:240px; overflow-y:auto;"></div>
    `;

    document.getElementById("addNoteBtn").addEventListener("click", function () {
        const txt = document.getElementById("newNoteText").value.trim();
        if (!txt) { alert("Note cannot be empty"); return; }
        addNote(txt);
    });

    document.getElementById("noteSearchInput").addEventListener("input", filterAndRenderNotes);
    loadNotes();
}

function loadNotes() {
    fetch("/api/notes")
        .then(r => r.json())
        .then(data => {
            allNotes = data || [];
            filterAndRenderNotes();
        })
        .catch(err => {
            const status = document.getElementById("notesStatus");
            if (status) status.textContent = "Error loading notes";
            console.error(err);
        });
}

function filterAndRenderNotes() {
    const list = document.getElementById("notesList");
    if (!list) return;
    const query = (document.getElementById("noteSearchInput")?.value || "").toLowerCase();
    const filtered = allNotes.filter(n => n.content.toLowerCase().includes(query));

    list.innerHTML = "";
    if (filtered.length === 0) {
        list.innerHTML = "<p style='color:#a99ec2; font-size:13px;'>No notes found.</p>";
        return;
    }

    filtered.forEach(note => {
        const div = document.createElement("div");
        div.style.cssText = "background:#2a1c40; padding:10px 12px; border-radius:8px; margin:8px 0; border:1px solid #3d2b59;";

        const updatedDate = new Date(note.updated_at || note.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' });
        
        const header = document.createElement("div");
        header.style.cssText = "display:flex; justify-content:space-between; margin-bottom:6px; font-size:11px; color:#b9a6d5;";
        header.innerHTML = `<span>Note #${note.id}</span> <span>${updatedDate}</span>`;

        const textarea = document.createElement("textarea");
        textarea.className = "nexus-input";
        textarea.value = note.content;
        textarea.style.cssText = "width:100%; height:70px; resize:vertical; font-size:13px; margin-bottom:8px;";

        const btnRow = document.createElement("div");
        btnRow.style.cssText = "display:flex; gap:6px; justify-content:flex-end;";

        const saveBtn = document.createElement("button");
        saveBtn.className = "nexus-btn";
        saveBtn.style.padding = "4px 10px";
        saveBtn.textContent = "💾 Save";
        saveBtn.addEventListener("click", () => updateNote(note.id, textarea.value));

        const delBtn = document.createElement("button");
        delBtn.className = "nexus-btn nexus-btn-danger";
        delBtn.style.padding = "4px 10px";
        delBtn.textContent = "🗑 Delete";
        delBtn.addEventListener("click", () => deleteNote(note.id));

        btnRow.appendChild(saveBtn);
        btnRow.appendChild(delBtn);

        div.appendChild(header);
        div.appendChild(textarea);
        div.appendChild(btnRow);
        list.appendChild(div);
    });
}

function addNote(content) {
    fetch("/api/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content })
    })
        .then(r => {
            if (!r.ok) throw new Error("Failed to add note");
            return r.json();
        })
        .then(() => {
            document.getElementById("newNoteText").value = "";
            showToast("Note created!", "success");
            loadNotes();
        })
        .catch(err => {
            const status = document.getElementById("notesStatus");
            if (status) status.textContent = err.message;
        });
}

function updateNote(id, content) {
    fetch(`/api/notes/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content })
    })
        .then(r => { if (!r.ok) throw new Error("Update failed"); return r.json(); })
        .then(() => {
            showToast("Note saved!", "success");
            loadNotes();
        })
        .catch(err => alert("Error updating note: " + err.message));
}

function deleteNote(id) {
    if (!confirm("Are you sure you want to delete this note?")) return;
    fetch(`/api/notes/${id}`, { method: "DELETE" })
        .then(r => { if (!r.ok) throw new Error("Delete failed"); return r.json(); })
        .then(() => {
            showToast("Note deleted.", "info");
            loadNotes();
        })
        .catch(err => alert("Error deleting note: " + err.message));
}

// =================================
// WINDOW CONTROLS & TASKBAR
// =================================

function closeApp() {
    const win = document.getElementById("appWindow");
    win.hidden = true;
    win.classList.remove("assistant-window-expanded");
    if (typeof stopSpeechRecognition === 'function') {
        stopSpeechRecognition();
    }
    if (typeof stopVoiceRecording === 'function') {
        stopVoiceRecording(false);
    }
    if (activeApp) {
        runningApps.delete(activeApp);
        activeApp = null;
        updateTaskbarApps();
    }
    if (isMaximized) {
        maximizeApp();
    }
}

function minimizeApp() {
    const win = document.getElementById("appWindow");
    win.hidden = true;
    updateTaskbarApps();
}

function maximizeApp() {
    const win = document.getElementById("appWindow");
    isMaximized = !isMaximized;
    if (isMaximized) {
        win.classList.add("window-maximized");
    } else {
        win.classList.remove("window-maximized");
        win.style.top = "80px";
        win.style.left = "50%";
        win.style.transform = "translateX(-50%)";
    }
}

function updateTaskbarApps() {
    const container = document.getElementById("taskbarRunningApps");
    if (!container) return;
    container.innerHTML = "";
    runningApps.forEach(appName => {
        const btn = document.createElement("button");
        btn.className = "nexus-btn";
        btn.style.padding = "4px 10px";
        btn.style.fontSize = "11px";
        btn.style.borderRadius = "6px";
        const isVisible = !document.getElementById("appWindow").hidden && activeApp === appName;
        btn.style.background = isVisible ? "#68449b" : "#2a1c40";
        btn.textContent = appName;
        btn.onclick = () => {
            const win = document.getElementById("appWindow");
            if (activeApp === appName && !win.hidden) {
                minimizeApp();
            } else {
                openApp(appName);
            }
        };
        container.appendChild(btn);
    });
}


// =================================
// DRAGGABLE APPLICATION WINDOW
// =================================

const win = document.getElementById("appWindow");
const header = document.getElementById("windowHeader");
let dragging = false;
let offsetX = 0;
let offsetY = 0;

header.addEventListener("mousedown", function (e) {
    if (e.target.tagName === "BUTTON") return;
    dragging = true;
    const rect = win.getBoundingClientRect();
    offsetX = e.clientX - rect.left;
    offsetY = e.clientY - rect.top;
    win.style.transform = "none";
});

document.addEventListener("mousemove", function (e) {
    if (!dragging || win.hidden) return;
    const area = document.querySelector(".desktop-area");
    const rect = area.getBoundingClientRect();
    win.style.left = Math.max(0, Math.min(e.clientX - rect.left - offsetX, rect.width - win.offsetWidth)) + "px";
    win.style.top = Math.max(0, e.clientY - rect.top - offsetY) + "px";
});

document.addEventListener("mouseup", function () { dragging = false; });

// =================================
// NEXUS FILE MANAGER (Backend-Integrated)
// =================================

let serverFiles = [];
let activeFileId = null;
let activeCategoryFilter = "all";

function showFileManager() {
    const content = document.getElementById("windowContent");
    content.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <h3 style="margin:0; font-size:17px;">📁 NEXUS AI File Intelligence & Manager</h3>
            <span style="font-size:11px; color:#c4a5ff;">PDF, DOCX, CSV, JSON, MD, PY, JS, TXT</span>
        </div>
        <p style="color:#b9a6d5; font-size:12px; margin-bottom:10px;">Extract content, generate AI summaries, search semantically, and interrogate documents using Gemini AI.</p>
        
        <!-- Upload Card -->
        <div style="background:#191228; padding:12px; border-radius:8px; margin-bottom:12px; border:1px solid #3d2b59;">
            <label style="font-size:12px; font-weight:bold; display:block; margin-bottom:6px; color:#d8b4fe;">Upload & Analyze Document:</label>
            <div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center;">
                <input type="file" id="serverFilePicker" style="font-size:12px; flex:1; min-width:200px;">
                <button id="uploadFileBtn" class="nexus-btn" style="padding:5px 12px;">⬆ Upload & Ingest with AI</button>
                <span id="uploadStatus" style="font-size:12px; color:#c4a5ff;"></span>
            </div>
        </div>

        <!-- Search & Category Filters -->
        <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px; align-items:center;">
            <input type="text" id="fileSearch" class="nexus-input" placeholder="🔍 Search files or ask in natural language (e.g. 'python files', 'pdf')..." style="flex:1; min-width:220px;">
            <button id="refreshFilesBtn" class="nexus-btn" style="padding:4px 10px; font-size:11px;">🔄 Refresh</button>
        </div>
        <div style="display:flex; gap:6px; margin-bottom:12px; overflow-x:auto;">
            <button class="nexus-btn file-filter-btn" data-cat="all" style="padding:2px 8px; font-size:10px; background:#6b3bb5;">All</button>
            <button class="nexus-btn file-filter-btn" data-cat="Code" style="padding:2px 8px; font-size:10px;">🐍 Code</button>
            <button class="nexus-btn file-filter-btn" data-cat="Document" style="padding:2px 8px; font-size:10px;">📄 Document</button>
            <button class="nexus-btn file-filter-btn" data-cat="Data" style="padding:2px 8px; font-size:10px;">📊 Data</button>
            <button class="nexus-btn file-filter-btn" data-cat="Notes" style="padding:2px 8px; font-size:10px;">📝 Notes</button>
        </div>

        <!-- Stored Files List -->
        <h4 style="margin:8px 0; font-size:13px; color:#e2d9f3;">Stored Documents & Intelligence</h4>
        <div id="fileList" style="max-height:200px; overflow-y:auto; margin-bottom:12px; padding-right:4px;"></div>
        
        <!-- Day 11: Secure Local Document Search & SQLite Indexing -->
        <div class="local-doc-search-box" style="background:#191228; border:1px solid #4a336e; border-radius:8px; padding:12px; margin-bottom:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <h4 style="margin:0; font-size:13px; color:#d8b4fe;">🔒 Secure Local Document Search</h4>
                <span style="font-size:10px; color:#c4a5ff; background:#2a1b44; padding:2px 6px; border-radius:4px;">SQLite Index • Zero Cloud Upload</span>
            </div>
            <p style="color:#b9a6d5; font-size:11px; margin:0 0 10px 0;">
                Select local text documents to index their contents directly into SQLite, then search inside them instantly. Files are stored locally and never sent to external servers.
            </p>

            <!-- Document Selection & Indexing Controls -->
            <div style="background:#120c1e; border:1px solid #3d2b59; border-radius:6px; padding:10px; margin-bottom:10px;">
                <label style="font-size:11px; font-weight:600; color:#e2d9f3; display:block; margin-bottom:6px;">
                    1. Select Document to Index:
                </label>
                <div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:6px;">
                    <input type="file" id="localDocPicker" accept=".txt,.md" style="font-size:11px; color:#e2d9f3; flex:1; min-width:200px;">
                    <button id="indexLocalDocBtn" class="nexus-btn" style="padding:5px 12px; font-size:11px; background:#6b3bb5;">
                        📥 Index Selected Document
                    </button>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:4px; font-size:10px;">
                    <span style="color:#a792c9;">ℹ️ Supported: <strong>.txt, .md</strong> (UTF-8 plain text only, Max 1 MB)</span>
                    <span id="indexingStatus" style="font-weight:600;"></span>
                </div>
            </div>

            <!-- Search Inside Indexed Documents -->
            <div style="background:#120c1e; border:1px solid #3d2b59; border-radius:6px; padding:10px;">
                <label style="font-size:11px; font-weight:600; color:#e2d9f3; display:block; margin-bottom:6px;">
                    2. Search Inside Indexed Documents:
                </label>
                <div style="display:flex; gap:8px; margin-bottom:8px;">
                    <input type="text" id="docSearchInput" class="nexus-input" placeholder="Search keywords in indexed documents (e.g. 'python', 'function')..." style="flex:1; font-size:12px;">
                    <button id="docSearchBtn" class="nexus-btn" style="padding:4px 14px; font-size:12px;">
                        🔍 Search
                    </button>
                </div>
                <div id="docSearchResults" style="display:none; max-height:160px; overflow-y:auto; padding-right:4px;"></div>
            </div>

            <!-- Day 12: My Documents (Indexed Library) -->
            <div style="background:#120c1e; border:1px solid #3d2b59; border-radius:6px; padding:10px; margin-top:10px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <div style="display:flex; align-items:center; gap:6px;">
                        <span style="font-size:12px; font-weight:bold; color:#e2d9f3;">📚 My Documents</span>
                        <span id="indexedDocsCountBadge" style="font-size:10px; color:#c4a5ff; background:#2a1b44; border:1px solid #4a336e; padding:1px 6px; border-radius:10px;">0 documents</span>
                    </div>
                    <button id="refreshIndexedDocsBtn" class="nexus-btn" style="padding:2px 8px; font-size:10px;">
                        🔄 Refresh
                    </button>
                </div>
                <div id="indexedDocsLibraryList" style="max-height:180px; overflow-y:auto; padding-right:4px;">
                    <div style="text-align:center; padding:12px; color:#9d8bb8; font-size:11px;">
                        <em>Loading indexed documents...</em>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Interactive Intelligence Workspace -->
        <div id="fileIntelligenceWorkspace" style="display:none; background:#191228; border:1px solid #4a336e; border-radius:8px; padding:12px; margin-top:8px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; border-bottom:1px solid #3d2b59; padding-bottom:6px;">
                <span id="activeFileTitle" style="font-weight:bold; color:#d8b4fe; font-size:13px;">Selected File</span>
                <div style="display:flex; gap:6px;">
                    <button id="tabPreviewBtn" class="nexus-btn" style="padding:2px 8px; font-size:10px;">👁️ Extracted Text</button>
                    <button id="tabSummaryBtn" class="nexus-btn" style="padding:2px 8px; font-size:10px;">✨ AI Summary</button>
                    <button id="tabAskBtn" class="nexus-btn" style="padding:2px 8px; font-size:10px; background:#6b3bb5;">🤖 Ask AI</button>
                    <button onclick="closeFileWorkspace()" class="nexus-btn nexus-btn-danger" style="padding:2px 6px; font-size:10px;">✕ Close</button>
                </div>
            </div>

            <!-- Tab 1: Extracted Text Preview -->
            <div id="panelPreview" style="display:none;">
                <div id="filePreviewContent" style="background:#120c1e; padding:10px; border-radius:6px; min-height:80px; max-height:180px; overflow:auto; font-size:12px; color:#e2d9f3; font-family:monospace; white-space:pre-wrap;"></div>
            </div>

            <!-- Tab 2: AI Summary & Metadata -->
            <div id="panelSummary" style="display:none;">
                <div id="fileSummaryContent" style="font-size:12px; line-height:1.5;"></div>
                <div style="margin-top:8px; text-align:right;">
                    <button id="reanalyzeBtn" class="nexus-btn" style="padding:3px 8px; font-size:11px;">🔄 Re-analyze with AI</button>
                </div>
            </div>

            <!-- Tab 3: Ask AI About This File -->
            <div id="panelAskAI">
                <p style="font-size:11px; color:#b9a6d5; margin:0 0 6px 0;">Ask questions about this file. Gemini will answer strictly based on the extracted document content.</p>
                <div style="display:flex; gap:6px; margin-bottom:8px;">
                    <input type="text" id="fileAIQuestionInput" class="nexus-input" placeholder="e.g., What are the key points? Explain this code..." style="flex:1; font-size:12px;" />
                    <button id="askFileAIBtn" class="nexus-btn" style="padding:4px 12px; font-size:12px;">Ask</button>
                </div>
                <div id="fileAIAnswerBox" style="background:#120c1e; border:1px solid #3d2b59; border-radius:6px; padding:10px; min-height:60px; max-height:160px; overflow:auto; font-size:12px; line-height:1.5; color:#f3e8ff;">
                    <em>Enter a question above to interrogate this document.</em>
                </div>
            </div>
        </div>
    `;

    document.getElementById("uploadFileBtn").addEventListener("click", uploadSelectedFile);
    document.getElementById("refreshFilesBtn").addEventListener("click", loadServerFiles);

    // Search input (supports natural language and keyword search)
    const searchInput = document.getElementById("fileSearch");
    if (searchInput) {
        let debounceTimer;
        searchInput.addEventListener("input", function () {
            clearTimeout(debounceTimer);
            const query = this.value.trim();
            debounceTimer = setTimeout(() => {
                if (query.length > 0) {
                    searchServerFiles(query);
                } else {
                    renderServerFileList(serverFiles);
                }
            }, 300);
        });
    }

    // Category filter buttons
    document.querySelectorAll(".file-filter-btn").forEach(btn => {
        btn.addEventListener("click", function () {
            document.querySelectorAll(".file-filter-btn").forEach(b => b.style.background = "");
            this.style.background = "#6b3bb5";
            activeCategoryFilter = this.getAttribute("data-cat");
            applyCategoryFilter();
        });
    });

    // Workspace tab switching
    document.getElementById("tabPreviewBtn").addEventListener("click", () => switchWorkspaceTab("preview"));
    document.getElementById("tabSummaryBtn").addEventListener("click", () => switchWorkspaceTab("summary"));
    document.getElementById("tabAskBtn").addEventListener("click", () => switchWorkspaceTab("ask"));

    document.getElementById("askFileAIBtn").addEventListener("click", submitFileAIQuestion);
    document.getElementById("fileAIQuestionInput").addEventListener("keydown", e => {
        if (e.key === "Enter") submitFileAIQuestion();
    });

    // Day 11: Document Indexing & Search Listeners
    const indexDocBtn = document.getElementById("indexLocalDocBtn");
    if (indexDocBtn) indexDocBtn.addEventListener("click", indexSelectedLocalDocument);

    const docSearchBtn = document.getElementById("docSearchBtn");
    if (docSearchBtn) docSearchBtn.addEventListener("click", searchIndexedDocuments);

    const docSearchInput = document.getElementById("docSearchInput");
    if (docSearchInput) {
        docSearchInput.addEventListener("keydown", e => {
            if (e.key === "Enter") searchIndexedDocuments();
        });
    }

    // Day 12: My Documents Library Listeners
    const refreshIndexedDocsBtn = document.getElementById("refreshIndexedDocsBtn");
    if (refreshIndexedDocsBtn) {
        refreshIndexedDocsBtn.addEventListener("click", loadIndexedDocumentsLibrary);
    }

    loadServerFiles();
    loadIndexedDocumentsLibrary();
}

// -----------------------------
// DAY 11: SECURE LOCAL DOCUMENT SEARCH & SQLITE INDEXING
// -----------------------------

async function indexSelectedLocalDocument() {
    const filePicker = document.getElementById("localDocPicker");
    const statusEl = document.getElementById("indexingStatus");
    if (!filePicker || !filePicker.files || filePicker.files.length === 0) {
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#ff5c7c;">⚠️ Please select a .txt or .md document first.</span>';
        }
        return;
    }

    const file = filePicker.files[0];
    const fileName = file.name || "";
    const lowerName = fileName.toLowerCase();
    if (!lowerName.endsWith(".txt") && !lowerName.endsWith(".md")) {
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#ff5c7c;">❌ Unsupported file type. Only .txt and .md files are supported.</span>';
        }
        return;
    }

    // Limit individual file size to 1 MB
    const maxBytes = 1 * 1024 * 1024;
    if (file.size > maxBytes) {
        if (statusEl) {
            statusEl.innerHTML = `<span style="color:#ff5c7c;">❌ File size (${(file.size / 1024).toFixed(1)} KB) exceeds the 1 MB limit.</span>`;
        }
        return;
    }

    // Explicit user confirmation explaining local SQLite storage and privacy
    const confirmMessage = 
        `🔒 Confirm Local Document Indexing\n\n` +
        `Document: ${fileName}\n` +
        `Size: ${(file.size / 1024).toFixed(1)} KB\n\n` +
        `The text content of this document will be securely extracted and stored in your local SQLite database (nexus.db) for fast search inside NEXUS AI OS.\n\n` +
        `• No data is uploaded to external AI services or cloud servers.\n` +
        `• Document content stays strictly on your local machine.\n\n` +
        `Do you want to proceed with indexing?`;

    const userConfirmed = window.confirm(confirmMessage);
    if (!userConfirmed) {
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#b9a6d5;">Indexing cancelled by user.</span>';
        }
        return;
    }

    if (statusEl) {
        statusEl.innerHTML = '<span style="color:#c4a5ff;">⏳ Indexing document locally in SQLite...</span>';
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
        const response = await fetch("/api/files/index", {
            method: "POST",
            body: formData
        });

        const data = await response.json();
        if (response.ok && data.status === "success") {
            if (statusEl) {
                statusEl.innerHTML = `<span style="color:#4ade80;">✅ Successfully indexed "<strong>${escapeHtml(data.filename)}</strong>" in SQLite!</span>`;
            }
            showToastNotification(`📄 Indexed ${data.filename} in local SQLite`);
            filePicker.value = ""; // Reset file picker safely
            loadIndexedDocumentsLibrary(); // Refresh indexed documents library immediately
        } else {
            const errMsg = data.error || "Indexing failed";
            if (statusEl) {
                statusEl.innerHTML = `<span style="color:#ff5c7c;">❌ Error: ${escapeHtml(errMsg)}</span>`;
            }
        }
    } catch (err) {
        if (statusEl) {
            statusEl.innerHTML = `<span style="color:#ff5c7c;">❌ Network / Server Error: ${escapeHtml(err.message)}</span>`;
        }
    }
}

async function searchIndexedDocuments() {
    const inputEl = document.getElementById("docSearchInput");
    const resultsContainer = document.getElementById("docSearchResults");
    if (!inputEl || !resultsContainer) return;

    const query = inputEl.value.trim();
    if (!query) {
        resultsContainer.style.display = "block";
        resultsContainer.innerHTML = '<div style="color:#ff5c7c; font-size:11px; padding:6px;">⚠️ Please enter a search keyword.</div>';
        return;
    }

    resultsContainer.style.display = "block";
    resultsContainer.innerHTML = '<div style="color:#c4a5ff; font-size:11px; padding:6px;">🔍 Searching indexed document contents in SQLite...</div>';

    try {
        const response = await fetch(`/api/files/search?q=${encodeURIComponent(query)}`);
        const data = await response.json();

        if (!response.ok) {
            const err = data.error || "Search failed";
            resultsContainer.innerHTML = `<div style="color:#ff5c7c; font-size:11px; padding:6px;">❌ Error: ${escapeHtml(err)}</div>`;
            return;
        }

        const results = data.results || [];
        if (results.length === 0) {
            resultsContainer.innerHTML = `
                <div style="background:#120c1e; border:1px dashed #4a336e; border-radius:6px; padding:12px; text-align:center; color:#9d8bb8; font-size:11px;">
                    No matching documents found for "<strong>${escapeHtml(query)}</strong>".<br/>
                    <span style="font-size:10px; color:#786594;">Try another keyword or index additional .txt / .md files above.</span>
                </div>
            `;
            return;
        }

        resultsContainer.innerHTML = `
            <div style="font-size:11px; color:#c4a5ff; font-weight:600; margin-bottom:6px;">
                Found ${results.length} match${results.length === 1 ? '' : 'es'} for "<em>${escapeHtml(query)}</em>":
            </div>
            ${results.map(r => `
                <div style="background:#26183c; border:1px solid #4a336e; border-radius:6px; padding:8px 10px; margin-bottom:6px; transition:border 0.2s;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:600; font-size:12px; color:#f3e8ff;">📄 ${escapeHtml(r.filename)}</span>
                        <span style="font-size:10px; color:#c4a5ff; background:#120c1e; padding:2px 6px; border-radius:4px;">SQLite Index</span>
                    </div>
                    <div style="font-size:11px; color:#d8b4fe; margin-top:5px; background:#120c1e; padding:6px 8px; border-radius:4px; font-family:monospace; line-height:1.4; white-space:pre-wrap; word-break:break-word;">
                        ${escapeHtml(r.snippet)}
                    </div>
                </div>
            `).join('')}
        `;
    } catch (err) {
        resultsContainer.innerHTML = `<div style="color:#ff5c7c; font-size:11px; padding:6px;">❌ Search Error: ${escapeHtml(err.message)}</div>`;
    }
}

// -----------------------------
// DAY 12: INDEXED DOCUMENTS LIBRARY & REMOVAL
// -----------------------------

async function loadIndexedDocumentsLibrary() {
    const listEl = document.getElementById("indexedDocsLibraryList");
    const countBadge = document.getElementById("indexedDocsCountBadge");
    if (!listEl) return;

    listEl.innerHTML = '<div style="text-align:center; padding:12px; color:#c4a5ff; font-size:11px;">⏳ Loading indexed documents...</div>';

    try {
        const response = await fetch("/api/files/list");
        const data = await response.json();

        if (!response.ok) {
            listEl.innerHTML = `<div style="color:#ff5c7c; font-size:11px; padding:10px; text-align:center;">Failed to load documents: ${escapeHtml(data.error || "Unknown error")}</div>`;
            return;
        }

        const docs = data.documents || [];
        const total = data.total !== undefined ? data.total : docs.length;

        if (countBadge) {
            countBadge.textContent = `${total} document${total === 1 ? '' : 's'}`;
        }

        if (docs.length === 0) {
            listEl.innerHTML = `
                <div style="text-align:center; padding:16px 8px; color:#9d8bb8; font-size:11px; border:1px dashed #3d2b59; border-radius:6px; background:#181028;">
                    📄 No documents indexed yet.<br/>
                    <span style="font-size:10px; color:#786594;">Select and index a .txt or .md document above to build your private search library.</span>
                </div>
            `;
            return;
        }

        listEl.innerHTML = docs.map(doc => `
            <div class="indexed-doc-card" style="background:#26183c; border:1px solid #4a336e; border-radius:6px; padding:8px 10px; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center; transition:border 0.2s;">
                <div style="min-width:0; flex:1; margin-right:8px;">
                    <div style="font-weight:600; font-size:12px; color:#f3e8ff; display:flex; align-items:center; gap:6px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                        <span>📄</span>
                        <span title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</span>
                    </div>
                    <div style="font-size:10px; color:#a792c9; margin-top:2px;">
                        Indexed: ${escapeHtml(doc.indexed_at || 'Recently')} • <span style="color:#38bdf8;">SQLite Index</span>
                    </div>
                </div>
                <div>
                    <button class="nexus-btn nexus-btn-danger" style="padding:3px 8px; font-size:10px; white-space:nowrap;" onclick="removeDocumentFromIndex(${doc.id}, '${escapeHtml(doc.filename).replace(/'/g, "\\'")}')">
                        🗑️ Remove from Index
                    </button>
                </div>
            </div>
        `).join('');

    } catch (err) {
        listEl.innerHTML = `<div style="color:#ff5c7c; font-size:11px; padding:10px; text-align:center;">Failed to connect to server: ${escapeHtml(err.message)}</div>`;
    }
}

async function removeDocumentFromIndex(documentId, filename) {
    const confirmMessage = 
        `Remove "${filename}" from NEXUS Search Index?\n\n` +
        `Notice: This action ONLY removes the document from your local search index (SQLite).\n` +
        `The original physical file on your computer will NOT be deleted or modified.\n\n` +
        `Do you want to proceed?`;

    const userConfirmed = window.confirm(confirmMessage);
    if (!userConfirmed) return;

    try {
        const response = await fetch(`/api/files/index/${encodeURIComponent(documentId)}?confirm=true`, {
            method: "DELETE"
        });

        const data = await response.json();
        if (response.ok && data.status === "success") {
            showToastNotification(`🗑️ Removed "${filename}" from search index`);
            loadIndexedDocumentsLibrary();
        } else {
            alert(`Failed to remove document: ${data.error || "Unknown error"}`);
        }
    } catch (err) {
        alert(`Network error while removing document: ${err.message}`);
    }
}

function switchWorkspaceTab(tab) {
    const preview = document.getElementById("panelPreview");
    const summary = document.getElementById("panelSummary");
    const ask = document.getElementById("panelAskAI");
    const tabPrev = document.getElementById("tabPreviewBtn");
    const tabSum = document.getElementById("tabSummaryBtn");
    const tabAsk = document.getElementById("tabAskBtn");

    if (preview) preview.style.display = (tab === "preview") ? "block" : "none";
    if (summary) summary.style.display = (tab === "summary") ? "block" : "none";
    if (ask) ask.style.display = (tab === "ask") ? "block" : "none";

    if (tabPrev) tabPrev.style.background = (tab === "preview") ? "#6b3bb5" : "";
    if (tabSum) tabSum.style.background = (tab === "summary") ? "#6b3bb5" : "";
    if (tabAsk) tabAsk.style.background = (tab === "ask") ? "#6b3bb5" : "";
}

function closeFileWorkspace() {
    const ws = document.getElementById("fileIntelligenceWorkspace");
    if (ws) ws.style.display = "none";
    activeFileId = null;
}

function loadServerFiles() {
    const list = document.getElementById("fileList");
    if (!list) return;
    list.innerHTML = "<em>Loading files & intelligence...</em>";
    fetch("/api/files")
        .then(r => r.json())
        .then(files => {
            serverFiles = files || [];
            applyCategoryFilter();
        })
        .catch(err => {
            list.innerHTML = `<span style="color:#ff5c7c;">Failed to load files: ${escapeHtml(err.message)}</span>`;
        });
}

function searchServerFiles(query) {
    const list = document.getElementById("fileList");
    if (!list) return;
    list.innerHTML = "<em>Searching files...</em>";
    fetch(`/api/files/uploaded-search?q=${encodeURIComponent(query)}`)
        .then(r => r.json())
        .then(files => {
            renderServerFileList(files || []);
        })
        .catch(err => {
            list.innerHTML = `<span style="color:#ff5c7c;">Search error: ${escapeHtml(err.message)}</span>`;
        });
}

function applyCategoryFilter() {
    if (activeCategoryFilter === "all") {
        renderServerFileList(serverFiles);
    } else {
        const filtered = serverFiles.filter(f => (f.category || "General").toLowerCase() === activeCategoryFilter.toLowerCase());
        renderServerFileList(filtered);
    }
}

function renderServerFileList(files) {
    const list = document.getElementById("fileList");
    if (!list) return;
    list.innerHTML = "";
    if (files.length === 0) {
        list.innerHTML = "<p style='color:#a99ec2; font-size:12px; padding:10px 0;'>No matching files found.</p>";
        return;
    }

    files.forEach(file => {
        const card = document.createElement("div");
        card.className = "file-card";

        const sizeKb = (file.size / 1024).toFixed(1);
        const cat = file.category || "General";
        let catBadgeClass = "file-badge-general";
        let catIcon = "📄";
        if (cat === "Code") { catBadgeClass = "file-badge-code"; catIcon = "🐍"; }
        else if (cat === "Document") { catBadgeClass = "file-badge-doc"; catIcon = "📄"; }
        else if (cat === "Data") { catBadgeClass = "file-badge-data"; catIcon = "📊"; }
        else if (cat === "Notes") { catBadgeClass = "file-badge-notes"; catIcon = "📝"; }

        // Keywords tags
        let keywordsHtml = "";
        if (file.keywords) {
            const kws = file.keywords.split(",").map(k => k.trim()).filter(Boolean).slice(0, 5);
            keywordsHtml = kws.map(k => `<span class="file-keyword-tag">#${escapeHtml(k)}</span>`).join(" ");
        }

        // Summary snippet
        let summarySnippet = file.summary ? `<div style="font-size:11px; color:#c4a5ff; margin-top:4px; line-height:1.4;">${escapeHtml(file.summary.slice(0, 140))}${file.summary.length > 140 ? '...' : ''}</div>` : "";

        card.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:4px;">
                <div>
                    <span class="file-badge ${catBadgeClass}">${catIcon} ${escapeHtml(cat)}</span>
                    <strong style="color:#f3e8ff; font-size:13px;">${escapeHtml(file.filename)}</strong>
                    <span style="font-size:11px; color:#b9a6d5; margin-left:6px;">(${sizeKb} KB - ${new Date(file.uploaded_at).toLocaleDateString()})</span>
                </div>
                <div style="display:flex; gap:4px; flex-wrap:wrap;">
                    <button class="nexus-btn btn-preview" style="padding:2px 6px; font-size:10px;">👁️ Preview</button>
                    <button class="nexus-btn btn-summary" style="padding:2px 6px; font-size:10px;">✨ AI Summary</button>
                    <button class="nexus-btn btn-ask" style="padding:2px 6px; font-size:10px; background:#6b3bb5;">🤖 Ask AI</button>
                    <a href="/api/files/${encodeURIComponent(file.filename)}" download="${escapeHtml(file.filename)}" class="nexus-btn" style="padding:2px 6px; font-size:10px; text-decoration:none;">⬇</a>
                    <button class="nexus-btn nexus-btn-danger btn-delete" style="padding:2px 6px; font-size:10px;">🗑</button>
                </div>
            </div>
            ${summarySnippet}
            <div style="margin-top:4px;">${keywordsHtml}</div>
        `;

        card.querySelector(".btn-preview").onclick = () => openFilePreview(file.id, file.filename, file.mime);
        card.querySelector(".btn-summary").onclick = () => openFileSummary(file.id, file.filename);
        card.querySelector(".btn-ask").onclick = () => openAskAIPanel(file.id, file.filename);
        card.querySelector(".btn-delete").onclick = () => deleteServerFile(file.id, file.filename);

        list.appendChild(card);
    });
}

function uploadSelectedFile() {
    const picker = document.getElementById("serverFilePicker");
    const status = document.getElementById("uploadStatus");
    if (!picker.files || picker.files.length === 0) {
        showToastNotification("⚠️ Please choose a file to upload.");
        return;
    }
    const file = picker.files[0];
    const formData = new FormData();
    formData.append("file", file);

    status.innerHTML = "<em>Analyzing & extracting content with AI...</em>";
    fetch("/api/files/upload", {
        method: "POST",
        body: formData
    })
    .then(r => {
        if (!r.ok) return r.json().then(e => { throw new Error(e.error || "Upload failed"); });
        return r.json();
    })
    .then(data => {
        status.innerHTML = `<span style="color:#4ade80;">✓ Extracted & categorized as <strong>${escapeHtml(data.category)}</strong>!</span>`;
        picker.value = "";
        loadServerFiles();
        showToastNotification(`✨ File ${data.filename} indexed and analyzed!`);
        setTimeout(() => { if (status) status.innerHTML = ""; }, 4000);
    })
    .catch(err => {
        status.innerHTML = `<span style="color:#ff5c7c;">Error: ${escapeHtml(err.message)}</span>`;
    });
}

function openFilePreview(fileId, filename, mime) {
    activeFileId = fileId;
    const ws = document.getElementById("fileIntelligenceWorkspace");
    const title = document.getElementById("activeFileTitle");
    const previewContent = document.getElementById("filePreviewContent");

    if (ws) ws.style.display = "block";
    if (title) title.innerHTML = `📄 ${escapeHtml(filename)} <span style="font-size:11px; color:#b9a6d5;">(Preview)</span>`;
    switchWorkspaceTab("preview");

    if (previewContent) {
        previewContent.innerHTML = "<em>Loading extracted content...</em>";
        fetch(`/api/files/${fileId}/content`)
            .then(r => r.json())
            .then(data => {
                const text = data.extracted_text || "";
                if (text) {
                    previewContent.innerHTML = `<div style="font-size:11px; color:#a879e5; margin-bottom:6px;">Extracted ${text.length} characters:</div>` + escapeHtml(text);
                } else if (mime && mime.startsWith("image/")) {
                    previewContent.innerHTML = `<img src="/api/files/${encodeURIComponent(filename)}" style="max-width:100%; max-height:160px; border-radius:6px; object-fit:contain;" alt="Preview" />`;
                } else {
                    previewContent.textContent = "No text content available to preview for this file type.";
                }
            })
            .catch(err => {
                previewContent.textContent = "Failed to load content: " + err.message;
            });
    }
}

function openFileSummary(fileId, filename) {
    activeFileId = fileId;
    const ws = document.getElementById("fileIntelligenceWorkspace");
    const title = document.getElementById("activeFileTitle");
    const summaryContent = document.getElementById("fileSummaryContent");
    const reanalyzeBtn = document.getElementById("reanalyzeBtn");

    if (ws) ws.style.display = "block";
    if (title) title.innerHTML = `✨ AI Summary: <strong>${escapeHtml(filename)}</strong>`;
    switchWorkspaceTab("summary");

    if (reanalyzeBtn) {
        reanalyzeBtn.onclick = () => triggerFileReanalysis(fileId, filename);
    }

    if (summaryContent) {
        summaryContent.innerHTML = "<em>Loading summary...</em>";
        fetch(`/api/files/${fileId}/content`)
            .then(r => r.json())
            .then(data => {
                const cat = data.category || "General";
                const summary = data.summary || "No summary available.";
                const keywords = data.keywords || "None";
                const keyInfo = data.key_info || "";

                summaryContent.innerHTML = `
                    <div style="margin-bottom:8px;">
                        <span class="file-badge file-badge-doc">Category: ${escapeHtml(cat)}</span>
                    </div>
                    <div style="margin-bottom:8px;">
                        <strong style="color:#d8b4fe;">Document Overview:</strong>
                        <p style="margin:4px 0 0 0; color:#f3e8ff;">${escapeHtml(summary)}</p>
                    </div>
                    ${keyInfo ? `
                    <div style="margin-bottom:8px;">
                        <strong style="color:#d8b4fe;">Key Information / Takeaways:</strong>
                        <div style="margin:4px 0 0 0; color:#e2d9f3;">${(typeof marked !== 'undefined') ? marked.parse(keyInfo) : escapeHtml(keyInfo)}</div>
                    </div>` : ''}
                    <div>
                        <strong style="color:#d8b4fe;">Keywords:</strong>
                        <span style="color:#b9a6d5;">${escapeHtml(keywords)}</span>
                    </div>
                `;
            })
            .catch(err => {
                summaryContent.textContent = "Failed to load summary: " + err.message;
            });
    }
}

function triggerFileReanalysis(fileId, filename) {
    const summaryContent = document.getElementById("fileSummaryContent");
    if (summaryContent) summaryContent.innerHTML = "<em>Re-analyzing document with Gemini AI... Please wait...</em>";
    fetch(`/api/files/${fileId}/summarize`, { method: "POST" })
        .then(r => r.json())
        .then(() => {
            openFileSummary(fileId, filename);
            loadServerFiles();
            showToastNotification("✨ Document re-analyzed successfully!");
        })
        .catch(err => {
            if (summaryContent) summaryContent.innerHTML = `<span style="color:#ff5c7c;">Re-analysis failed: ${escapeHtml(err.message)}</span>`;
        });
}

function openAskAIPanel(fileId, filename) {
    activeFileId = fileId;
    const ws = document.getElementById("fileIntelligenceWorkspace");
    const title = document.getElementById("activeFileTitle");
    const answerBox = document.getElementById("fileAIAnswerBox");
    const input = document.getElementById("fileAIQuestionInput");

    if (ws) ws.style.display = "block";
    if (title) title.innerHTML = `🤖 Ask AI About: <strong>${escapeHtml(filename)}</strong>`;
    switchWorkspaceTab("ask");

    if (answerBox) {
        answerBox.innerHTML = `
            <div style="color:#b9a6d5; font-size:12px;">
                Ready to answer questions about <strong>${escapeHtml(filename)}</strong>.
                <div style="margin-top:6px; display:flex; gap:6px; flex-wrap:wrap;">
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px;" onclick="setAskInput('What is the main summary of this document?')">Summarize</button>
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px;" onclick="setAskInput('List all key topics or functions mentioned in this file.')">Key topics</button>
                    <button class="nexus-btn" style="padding:2px 8px; font-size:10px;" onclick="setAskInput('Are there any critical warnings or important notes?')">Warnings / Notes</button>
                </div>
            </div>
        `;
    }
    if (input) input.focus();
}

function setAskInput(text) {
    const input = document.getElementById("fileAIQuestionInput");
    if (input) {
        input.value = text;
        input.focus();
    }
}

function submitFileAIQuestion() {
    if (!activeFileId) {
        showToastNotification("⚠️ Please select a file first.");
        return;
    }
    const input = document.getElementById("fileAIQuestionInput");
    const answerBox = document.getElementById("fileAIAnswerBox");
    const askBtn = document.getElementById("askFileAIBtn");

    const question = input ? input.value.trim() : "";
    if (!question) {
        showToastNotification("⚠️ Please enter a question.");
        return;
    }

    if (answerBox) {
        answerBox.innerHTML = `
            <div style="display:flex; align-items:center; gap:8px;">
                <div class="typing-indicator"><span></span><span></span><span></span></div>
                <em>NEXUS AI is reading the file and formulating an answer...</em>
            </div>
        `;
    }
    if (askBtn) askBtn.disabled = true;

    fetch(`/api/files/${activeFileId}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question })
    })
    .then(r => {
        if (!r.ok) return r.json().then(e => { throw new Error(e.error || "AI query failed"); });
        return r.json();
    })
    .then(data => {
        if (answerBox) {
            const rawContent = encodeURIComponent(data.reply);
            const rendered = (typeof marked !== 'undefined') ? marked.parse(data.reply) : escapeHtml(data.reply);
            answerBox.innerHTML = `
                <div style="margin-bottom:6px; border-bottom:1px solid #3d2b59; padding-bottom:4px; display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:11px; color:#c4a5ff;"><strong>Q:</strong> ${escapeHtml(question)}</span>
                    <button class="nexus-btn" style="padding:1px 6px; font-size:10px;" onclick="copyChatMessage(decodeURIComponent('${rawContent}'), this)">📋 Copy</button>
                </div>
                <div class="message-body" style="line-height:1.6;">${rendered}</div>
            `;
        }
    })
    .catch(err => {
        if (answerBox) {
            answerBox.innerHTML = `<span style="color:#ff5c7c;"><strong>Error:</strong> ${escapeHtml(err.message)}</span>`;
        }
    })
    .finally(() => {
        if (askBtn) askBtn.disabled = false;
    });
}

function deleteServerFile(fileId, filename) {
    if (!confirm(`Are you sure you want to delete '${filename}'?`)) return;
    fetch(`/api/files/${fileId}`, { method: "DELETE" })
        .then(r => r.json())
        .then(() => {
            showToastNotification(`🗑️ Deleted ${filename}`);
            if (activeFileId === fileId) closeFileWorkspace();
            loadServerFiles();
        })
        .catch(err => {
            showToastNotification(`⚠️ Delete failed: ${err.message}`);
        });
}

// =================================
// NEXUS TASK MANAGER (Phase 2)
// =================================

let allTasks = [];
let taskFilter = 'all'; // 'all', 'pending', 'completed'
let taskPriorityFilter = 'all';

function showTaskManager() {
    const content = document.getElementById("windowContent");
    content.innerHTML = `
        <h3>📋 NEXUS Task Manager</h3>
        <p style="color:#b9a6d5; font-size:12px; margin-bottom:12px;">Persistent Task Management with SQLite.</p>

        <!-- Task Stats -->
        <div style="display:flex; gap:10px; margin-bottom:14px;">
            <div style="flex:1; background:#191228; padding:8px 12px; border-radius:8px; border:1px solid #3d2b59; text-align:center;">
                <span style="font-size:11px; color:#b9a6d5;">Total Tasks</span>
                <div id="statTotalTasks" style="font-size:18px; font-weight:bold; color:#d8b4fe;">0</div>
            </div>
            <div style="flex:1; background:#191228; padding:8px 12px; border-radius:8px; border:1px solid #3d2b59; text-align:center;">
                <span style="font-size:11px; color:#b9a6d5;">Pending</span>
                <div id="statPendingTasks" style="font-size:18px; font-weight:bold; color:#dd6b20;">0</div>
            </div>
            <div style="flex:1; background:#191228; padding:8px 12px; border-radius:8px; border:1px solid #3d2b59; text-align:center;">
                <span style="font-size:11px; color:#b9a6d5;">Completed</span>
                <div id="statCompletedTasks" style="font-size:18px; font-weight:bold; color:#38a169;">0</div>
            </div>
        </div>

        <!-- Add Task Form -->
        <div style="background:#191228; padding:12px; border-radius:8px; margin-bottom:14px; border:1px solid #3d2b59;">
            <label style="font-size:12px; font-weight:bold; display:block; margin-bottom:6px;">Create New Task:</label>
            <div style="display:flex; flex-wrap:wrap; gap:8px;">
                <input type="text" id="taskTitleInput" class="nexus-input" placeholder="Task description..." style="flex:2; min-width:180px;">
                <select id="taskPrioritySelect" class="nexus-select" style="flex:1; min-width:90px;">
                    <option value="Low">Low</option>
                    <option value="Medium" selected>Medium</option>
                    <option value="High">High</option>
                </select>
                <input type="date" id="taskDueDateInput" class="nexus-input" style="flex:1; min-width:130px;">
                <button id="addTaskBtn" class="nexus-btn">➕ Add</button>
            </div>
            <span id="taskStatusMsg" style="font-size:12px; margin-top:4px; display:inline-block; color:#ff5c7c;"></span>
        </div>

        <!-- Filters & Search -->
        <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px; align-items:center;">
            <input type="text" id="taskSearchInput" class="nexus-input" placeholder="Search tasks..." style="flex:2; min-width:140px;">
            <select id="taskStatusFilterSelect" class="nexus-select" style="flex:1; min-width:100px;">
                <option value="all">All Status</option>
                <option value="pending">Pending</option>
                <option value="completed">Completed</option>
            </select>
            <select id="taskPriorityFilterSelect" class="nexus-select" style="flex:1; min-width:100px;">
                <option value="all">All Priorities</option>
                <option value="High">High</option>
                <option value="Medium">Medium</option>
                <option value="Low">Low</option>
            </select>
        </div>

        <!-- Task List -->
        <div id="taskList" style="max-height:220px; overflow-y:auto;"></div>
    `;

    document.getElementById("addTaskBtn").addEventListener("click", createTaskFromInput);
    document.getElementById("taskSearchInput").addEventListener("input", filterAndRenderTasks);
    document.getElementById("taskStatusFilterSelect").addEventListener("change", function () {
        taskFilter = this.value;
        filterAndRenderTasks();
    });
    document.getElementById("taskPriorityFilterSelect").addEventListener("change", function () {
        taskPriorityFilter = this.value;
        filterAndRenderTasks();
    });

    loadTasks();
}

function loadTasks() {
    const list = document.getElementById("taskList");
    if (!list) return;
    list.innerHTML = "<em>Loading tasks...</em>";
    fetch("/api/tasks")
        .then(r => r.json())
        .then(tasks => {
            allTasks = tasks || [];
            updateTaskStats();
            filterAndRenderTasks();
        })
        .catch(err => {
            list.innerHTML = `<span style="color:#ff5c7c;">Error loading tasks: ${err.message}</span>`;
        });
}

function updateTaskStats() {
    const total = allTasks.length;
    const completed = allTasks.filter(t => t.completed).length;
    const pending = total - completed;

    const elTotal = document.getElementById("statTotalTasks");
    const elPending = document.getElementById("statPendingTasks");
    const elCompleted = document.getElementById("statCompletedTasks");

    if (elTotal) elTotal.textContent = total;
    if (elPending) elPending.textContent = pending;
    if (elCompleted) elCompleted.textContent = completed;
}

function filterAndRenderTasks() {
    const list = document.getElementById("taskList");
    if (!list) return;

    const search = (document.getElementById("taskSearchInput")?.value || "").toLowerCase();
    const filtered = allTasks.filter(task => {
        const matchesSearch = task.title.toLowerCase().includes(search);
        const matchesStatus = taskFilter === 'all' ? true :
            taskFilter === 'completed' ? task.completed : !task.completed;
        const matchesPriority = taskPriorityFilter === 'all' ? true : task.priority === taskPriorityFilter;
        return matchesSearch && matchesStatus && matchesPriority;
    });

    list.innerHTML = "";
    if (filtered.length === 0) {
        list.innerHTML = "<p style='color:#a99ec2; font-size:13px;'>No tasks match criteria.</p>";
        return;
    }

    filtered.forEach(task => {
        const item = document.createElement("div");
        item.style.padding = "10px 12px";
        item.style.margin = "6px 0";
        item.style.background = task.completed ? "#1e172e" : "#2a1c40";
        item.style.borderLeft = `4px solid ${task.priority === 'High' ? '#e53e3e' : task.priority === 'Medium' ? '#dd6b20' : '#319795'}`;
        item.style.borderRadius = "6px";
        item.style.display = "flex";
        item.style.alignItems = "center";
        item.style.justifyContent = "space-between";
        item.style.gap = "10px";

        const left = document.createElement("div");
        left.style.display = "flex";
        left.style.alignItems = "center";
        left.style.gap = "8px";
        left.style.flex = "1";

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = !!task.completed;
        checkbox.style.cursor = "pointer";
        checkbox.onchange = () => toggleTaskCompletion(task.id, checkbox.checked);

        const titleSpan = document.createElement("span");
        titleSpan.textContent = task.title;
        titleSpan.style.fontSize = "13px";
        if (task.completed) {
            titleSpan.style.textDecoration = "line-through";
            titleSpan.style.color = "#8b7e9f";
        }

        const badge = document.createElement("span");
        badge.className = `badge-priority badge-${task.priority.toLowerCase()}`;
        badge.textContent = task.priority;

        left.appendChild(checkbox);
        left.appendChild(titleSpan);
        left.appendChild(badge);

        if (task.due_date) {
            const dueSpan = document.createElement("span");
            dueSpan.style.fontSize = "11px";
            dueSpan.style.color = "#c4a5ff";
            dueSpan.textContent = `📅 ${task.due_date}`;
            left.appendChild(dueSpan);
        }

        const right = document.createElement("div");
        right.style.display = "flex";
        right.style.gap = "6px";

        const editBtn = document.createElement("button");
        editBtn.className = "nexus-btn";
        editBtn.style.padding = "3px 8px";
        editBtn.style.fontSize = "11px";
        editBtn.textContent = "✏ Edit";
        editBtn.onclick = () => promptEditTask(task);

        const delBtn = document.createElement("button");
        delBtn.className = "nexus-btn nexus-btn-danger";
        delBtn.style.padding = "3px 8px";
        delBtn.style.fontSize = "11px";
        delBtn.textContent = "🗑";
        delBtn.onclick = () => deleteTask(task.id);

        right.appendChild(editBtn);
        right.appendChild(delBtn);
        item.appendChild(left);
        item.appendChild(right);
        list.appendChild(item);
    });
}

function createTaskFromInput() {
    const titleInput = document.getElementById("taskTitleInput");
    const prioritySelect = document.getElementById("taskPrioritySelect");
    const dateInput = document.getElementById("taskDueDateInput");
    const statusMsg = document.getElementById("taskStatusMsg");

    const title = titleInput.value.trim();
    if (!title) {
        if (statusMsg) statusMsg.textContent = "Task title cannot be empty.";
        return;
    }
    const priority = prioritySelect.value;
    const due_date = dateInput.value || null;

    fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, priority, due_date })
    })
        .then(r => {
            if (!r.ok) return r.json().then(e => { throw new Error(e.error || "Failed to create task"); });
            return r.json();
        })
        .then(() => {
            titleInput.value = "";
            dateInput.value = "";
            if (statusMsg) statusMsg.textContent = "";
            loadTasks();
        })
        .catch(err => {
            if (statusMsg) statusMsg.textContent = err.message;
        });
}

function toggleTaskCompletion(taskId, completed) {
    fetch(`/api/tasks/${taskId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ completed })
    })
        .then(r => r.json())
        .then(() => loadTasks())
        .catch(err => alert("Error updating task: " + err.message));
}

function promptEditTask(task) {
    const newTitle = prompt("Edit task description:", task.title);
    if (newTitle === null) return;
    const trimmed = newTitle.trim();
    if (!trimmed) {
        alert("Task description cannot be empty");
        return;
    }
    const newPriority = prompt("Edit priority (Low, Medium, High):", task.priority);
    if (!["Low", "Medium", "High"].includes(newPriority)) {
        alert("Priority must be Low, Medium, or High");
        return;
    }
    fetch(`/api/tasks/${task.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: trimmed, priority: newPriority })
    })
        .then(r => r.json())
        .then(() => loadTasks())
        .catch(err => alert("Error updating task: " + err.message));
}

function deleteTask(taskId) {
    if (!confirm("Are you sure you want to delete this task?")) return;
    fetch(`/api/tasks/${taskId}`, { method: "DELETE" })
        .then(r => r.json())
        .then(() => loadTasks())
        .catch(err => alert("Error deleting task: " + err.message));
}

// =================================
// NEXUS CALENDAR (Phase 2)
// =================================

let calendarDate = new Date();
let allEvents = [];

function showCalendar() {
    const content = document.getElementById("windowContent");
    content.innerHTML = `
        <h3>📅 NEXUS Calendar</h3>
        <p style="color:#b9a6d5; font-size:12px; margin-bottom:12px;">Persistent Event Scheduling with SQLite.</p>

        <!-- Month Navigation -->
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <button id="prevMonthBtn" class="nexus-btn">◀ Prev</button>
            <h4 id="calendarMonthTitle" style="color:#d8b4fe; margin:0;"></h4>
            <div style="display:flex; gap:6px;">
                <button id="todayMonthBtn" class="nexus-btn">Today</button>
                <button id="nextMonthBtn" class="nexus-btn">Next ▶</button>
            </div>
        </div>

        <!-- Calendar Grid -->
        <div class="calendar-grid" id="calendarGrid"></div>

        <!-- Add Event Form -->
        <div style="background:#191228; padding:12px; border-radius:8px; margin:14px 0; border:1px solid #3d2b59;">
            <label style="font-size:12px; font-weight:bold; display:block; margin-bottom:6px;">Schedule New Event:</label>
            <div style="display:flex; flex-direction:column; gap:8px;">
                <input type="text" id="eventTitleInput" class="nexus-input" placeholder="Event title..." style="width:100%;">
                <div style="display:flex; gap:8px; flex-wrap:wrap;">
                    <div style="flex:1; min-width:140px;">
                        <label style="font-size:11px; color:#b9a6d5; display:block;">Start:</label>
                        <input type="datetime-local" id="eventStartInput" class="nexus-input" style="width:100%;">
                    </div>
                    <div style="flex:1; min-width:140px;">
                        <label style="font-size:11px; color:#b9a6d5; display:block;">End:</label>
                        <input type="datetime-local" id="eventEndInput" class="nexus-input" style="width:100%;">
                    </div>
                </div>
                <button id="addEventBtn" class="nexus-btn" style="align-self:flex-start;">➕ Add Event</button>
                <span id="eventStatusMsg" style="font-size:12px; color:#ff5c7c;"></span>
            </div>
        </div>

        <!-- Upcoming Events Section -->
        <h4>Upcoming Events</h4>
        <div id="eventsList" style="max-height:160px; overflow-y:auto; margin-top:8px;"></div>
    `;

    document.getElementById("prevMonthBtn").addEventListener("click", () => {
        calendarDate.setMonth(calendarDate.getMonth() - 1);
        renderCalendar();
    });
    document.getElementById("nextMonthBtn").addEventListener("click", () => {
        calendarDate.setMonth(calendarDate.getMonth() + 1);
        renderCalendar();
    });
    document.getElementById("todayMonthBtn").addEventListener("click", () => {
        calendarDate = new Date();
        renderCalendar();
    });
    document.getElementById("addEventBtn").addEventListener("click", createEventFromInput);

    loadEvents();
}

function loadEvents() {
    fetch("/api/events")
        .then(r => r.json())
        .then(events => {
            allEvents = events || [];
            renderCalendar();
            renderEventsList();
        })
        .catch(err => {
            console.error("Error loading events", err);
        });
}

function renderCalendar() {
    const title = document.getElementById("calendarMonthTitle");
    const grid = document.getElementById("calendarGrid");
    if (!title || !grid) return;

    const year = calendarDate.getFullYear();
    const month = calendarDate.getMonth();
    const monthNames = ["January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"];
    title.textContent = `${monthNames[month]} ${year}`;

    grid.innerHTML = "";
    const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    dayNames.forEach(d => {
        const h = document.createElement("div");
        h.className = "calendar-header-day";
        h.textContent = d;
        grid.appendChild(h);
    });

    const firstDayIndex = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const today = new Date();

    // Blank cells before first day
    for (let i = 0; i < firstDayIndex; i++) {
        const blank = document.createElement("div");
        blank.style.opacity = "0.2";
        grid.appendChild(blank);
    }

    // Days in month
    for (let day = 1; day <= daysInMonth; day++) {
        const cell = document.createElement("div");
        cell.className = "calendar-day";
        cell.textContent = day;

        const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const isToday = today.getFullYear() === year && today.getMonth() === month && today.getDate() === day;
        if (isToday) cell.classList.add("today");

        const hasEvent = allEvents.some(e => e.start && e.start.startsWith(dateStr));
        if (hasEvent) cell.classList.add("has-event");

        cell.onclick = () => {
            const startInput = document.getElementById("eventStartInput");
            const endInput = document.getElementById("eventEndInput");
            if (startInput && endInput) {
                startInput.value = `${dateStr}T09:00`;
                endInput.value = `${dateStr}T10:00`;
            }
        };

        grid.appendChild(cell);
    }
}

function renderEventsList() {
    const list = document.getElementById("eventsList");
    if (!list) return;
    list.innerHTML = "";
    if (allEvents.length === 0) {
        list.innerHTML = "<p style='color:#a99ec2; font-size:13px;'>No scheduled events.</p>";
        return;
    }

    allEvents.forEach(evt => {
        const item = document.createElement("div");
        item.style.padding = "8px 12px";
        item.style.margin = "4px 0";
        item.style.background = "#2a1c40";
        item.style.borderRadius = "6px";
        item.style.display = "flex";
        item.style.justifyContent = "space-between";
        item.style.alignItems = "center";

        const info = document.createElement("div");
        const startFormatted = evt.start.replace("T", " ");
        const endFormatted = evt.end.replace("T", " ");
        info.innerHTML = `<strong>${escapeHtml(evt.title)}</strong><br/><span style="font-size:11px; color:#c4a5ff;">🕒 ${startFormatted} – ${endFormatted}</span>`;

        const btnGroup = document.createElement("div");
        btnGroup.style.display = "flex";
        btnGroup.style.gap = "6px";

        const editBtn = document.createElement("button");
        editBtn.className = "nexus-btn";
        editBtn.style.padding = "3px 8px";
        editBtn.style.fontSize = "11px";
        editBtn.textContent = "✏ Edit";
        editBtn.onclick = () => promptEditEvent(evt);

        const delBtn = document.createElement("button");
        delBtn.className = "nexus-btn nexus-btn-danger";
        delBtn.style.padding = "3px 8px";
        delBtn.style.fontSize = "11px";
        delBtn.textContent = "🗑";
        delBtn.onclick = () => deleteEvent(evt.id);

        btnGroup.appendChild(editBtn);
        btnGroup.appendChild(delBtn);
        item.appendChild(info);
        item.appendChild(btnGroup);
        list.appendChild(item);
    });
}

function createEventFromInput() {
    const titleInput = document.getElementById("eventTitleInput");
    const startInput = document.getElementById("eventStartInput");
    const endInput = document.getElementById("eventEndInput");
    const statusMsg = document.getElementById("eventStatusMsg");

    const title = titleInput.value.trim();
    const start = startInput.value;
    const end = endInput.value;

    if (!title) {
        if (statusMsg) statusMsg.textContent = "Please enter an event title.";
        return;
    }
    if (!start || !end) {
        if (statusMsg) statusMsg.textContent = "Please provide both start and end times.";
        return;
    }
    if (start >= end) {
        if (statusMsg) statusMsg.textContent = "Start time must precede end time.";
        return;
    }

    fetch("/api/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, start, end })
    })
        .then(r => {
            if (!r.ok) return r.json().then(e => { throw new Error(e.error || "Failed to create event"); });
            return r.json();
        })
        .then(() => {
            titleInput.value = "";
            startInput.value = "";
            endInput.value = "";
            if (statusMsg) statusMsg.textContent = "";
            loadEvents();
        })
        .catch(err => {
            if (statusMsg) statusMsg.textContent = err.message;
        });
}

function promptEditEvent(evt) {
    const newTitle = prompt("Edit event title:", evt.title);
    if (newTitle === null) return;
    const trimmed = newTitle.trim();
    if (!trimmed) {
        alert("Title cannot be empty");
        return;
    }
    fetch(`/api/events/${evt.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: trimmed })
    })
        .then(r => r.json())
        .then(() => loadEvents())
        .catch(err => alert("Error updating event: " + err.message));
}

function deleteEvent(eventId) {
    if (!confirm("Are you sure you want to delete this event?")) return;
    fetch(`/api/events/${eventId}`, { method: "DELETE" })
        .then(r => r.json())
        .then(() => loadEvents())
        .catch(err => alert("Error deleting event: " + err.message));
}


// =================================
// NEXUS NOTIFICATION SYSTEM
// =================================

let systemNotifications = [];

function showToast(message, type = "info") {
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    systemNotifications.unshift({ message, type, time: timestamp });

    const badge = document.getElementById("notifBadge");
    if (badge) badge.style.display = "block";

    let container = document.getElementById("toastContainer");
    if (!container) {
        container = document.createElement("div");
        container.id = "toastContainer";
        container.style.cssText = "position:fixed; bottom:20px; right:20px; z-index:9999; display:flex; flex-direction:column; gap:8px; pointer-events:none;";
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.style.cssText = "background:#211832; color:white; padding:10px 16px; border-radius:8px; border-left:4px solid #a879e5; box-shadow:0 6px 16px rgba(0,0,0,0.4); font-size:13px; pointer-events:auto; display:flex; align-items:center; gap:8px; transition:opacity 0.4s ease;";
    if (type === "success") toast.style.borderLeftColor = "#48bb78";
    if (type === "error") toast.style.borderLeftColor = "#ff5c7c";

    const icon = type === "success" ? "✅" : type === "error" ? "❌" : "ℹ️";
    toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 400);
    }, 3500);
}

function showNotificationCenter() {
    const badge = document.getElementById("notifBadge");
    if (badge) badge.style.display = "none";

    const content = document.getElementById("windowContent");
    content.innerHTML = `
        <h3>🔔 Notification Center</h3>
        <p style="color:#b9a6d5; font-size:12px; margin-bottom:12px;">System notifications and activity log.</p>
        
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <span style="font-size:13px; color:#d8b4fe;">Recent Alerts (${systemNotifications.length})</span>
            <button class="nexus-btn nexus-btn-danger" style="padding:3px 8px; font-size:11px;" onclick="clearNotifications()">Clear All</button>
        </div>

        <div id="notifList" style="max-height:260px; overflow-y:auto;"></div>
    `;

    renderNotificationList();
}

function renderNotificationList() {
    const list = document.getElementById("notifList");
    if (!list) return;
    list.innerHTML = "";
    if (systemNotifications.length === 0) {
        list.innerHTML = "<p style='color:#a99ec2; font-size:13px;'>No notifications yet.</p>";
        return;
    }
    systemNotifications.forEach(n => {
        const item = document.createElement("div");
        item.style.cssText = "background:#191228; padding:8px 12px; border-radius:6px; margin:4px 0; border:1px solid #3d2b59; display:flex; justify-content:space-between; align-items:center;";
        const icon = n.type === "success" ? "✅" : n.type === "error" ? "❌" : "ℹ️";
        item.innerHTML = `<span>${icon} ${escapeHtml(n.message)}</span><span style="font-size:11px; color:#a99ec2;">${n.time}</span>`;
        list.appendChild(item);
    });
}

function clearNotifications() {
    systemNotifications = [];
    renderNotificationList();
}

// =================================
// NEXUS SETTINGS & PREFERENCES
// =================================

function showSettings() {
    const content = document.getElementById("windowContent");
    const currentTheme = localStorage.getItem("nexusTheme") || "purple";
    const currentName = localStorage.getItem("nexusUserName") || "Commander";
    const currentClockFormat = localStorage.getItem("nexusClockFormat") || "12";
    const currentVoiceDefault = localStorage.getItem("nexusVoiceDefault") || "off";

    content.innerHTML = `
        <h3>⚙️ NEXUS Settings & Preferences</h3>
        <p style="color:#b9a6d5; font-size:12px; margin-bottom:14px;">Customize themes, identity profile, and system behavior.</p>

        <!-- Theme Selection -->
        <div style="background:#191228; padding:12px; border-radius:8px; margin-bottom:12px; border:1px solid #3d2b59;">
            <label style="font-size:13px; font-weight:bold; color:#d8b4fe; display:block; margin-bottom:6px;">🎨 Desktop Theme</label>
            <select id="themeSelect" class="nexus-select" style="width:100%;">
                <option value="purple">Purple Dark (Default)</option>
                <option value="blue">Deep Blue Neon</option>
                <option value="green">Emerald Matrix</option>
            </select>
        </div>

        <!-- User Profile -->
        <div style="background:#191228; padding:12px; border-radius:8px; margin-bottom:12px; border:1px solid #3d2b59;">
            <label style="font-size:13px; font-weight:bold; color:#d8b4fe; display:block; margin-bottom:6px;">👤 User Profile</label>
            <div style="display:flex; gap:8px;">
                <input type="text" id="userNameInput" class="nexus-input" placeholder="Display name..." value="${escapeHtml(currentName)}" style="flex:1;">
            </div>
        </div>

        <!-- AI Intelligence Engine (Secure backend environment) -->
        <div style="background:#191228; padding:12px; border-radius:8px; margin-bottom:12px; border:1px solid #3d2b59;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <label style="font-size:13px; font-weight:bold; color:#d8b4fe; display:block;">🤖 AI Intelligence Engine</label>
                    <p style="font-size:11px; color:#a99ec2; margin:3px 0 0 0;">Gemini 2.5 / 3.x Flash integrated securely via backend environment (.env). Credentials protected.</p>
                </div>
                <span id="geminiKeyStatus" style="font-size:11px; color:#4ade80; background:rgba(74,222,128,0.12); padding:3px 8px; border-radius:12px; border:1px solid rgba(74,222,128,0.25);">● Active & Secure</span>
            </div>
        </div>

        <!-- Application Preferences -->
        <div style="background:#191228; padding:12px; border-radius:8px; margin-bottom:14px; border:1px solid #3d2b59;">
            <label style="font-size:13px; font-weight:bold; color:#d8b4fe; display:block; margin-bottom:8px;">⚙️ Preferences</label>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; font-size:12px;">
                <div>
                    <label style="display:block; margin-bottom:4px; color:#b9a6d5;">Clock Format:</label>
                    <select id="clockFormatSelect" class="nexus-select" style="width:100%;">
                        <option value="12">12-Hour (AM/PM)</option>
                        <option value="24">24-Hour (Military)</option>
                    </select>
                </div>
                <div>
                    <label style="display:block; margin-bottom:4px; color:#b9a6d5;">AI Voice Default:</label>
                    <select id="voiceDefaultSelect" class="nexus-select" style="width:100%;">
                        <option value="off">Muted (Text only)</option>
                        <option value="on">Spoken (Text-to-speech)</option>
                    </select>
                </div>
            </div>
        </div>

        <div style="display:flex; gap:10px;">
            <button id="saveSettingsBtn" class="nexus-btn">💾 Save All Settings</button>
            <button id="resetSettingsBtn" class="nexus-btn nexus-btn-danger">Reset to Defaults</button>
        </div>
    `;

    document.getElementById("themeSelect").value = currentTheme;
    document.getElementById("clockFormatSelect").value = currentClockFormat;
    document.getElementById("voiceDefaultSelect").value = currentVoiceDefault;

    // Check Gemini backend configuration status (read-only verification)
    fetch("/api/settings/gemini-key")
        .then(r => r.json())
        .then(data => {
            const statusEl = document.getElementById("geminiKeyStatus");
            if (statusEl) {
                if (data.configured) {
                    statusEl.innerHTML = `🟢 Configured via .env (${data.masked})`;
                } else {
                    statusEl.innerHTML = `<span style="color:#fbbf24;">⚠️ Not configured in .env</span>`;
                }
            }
        })
        .catch(() => {});

    document.getElementById("saveSettingsBtn").addEventListener("click", () => {
        const theme = document.getElementById("themeSelect").value;
        const name = document.getElementById("userNameInput").value.trim() || "Commander";
        const clockFmt = document.getElementById("clockFormatSelect").value;
        const voiceDef = document.getElementById("voiceDefaultSelect").value;

        applyTheme(theme);
        localStorage.setItem("nexusUserName", name);
        localStorage.setItem("nexusClockFormat", clockFmt);
        localStorage.setItem("nexusVoiceDefault", voiceDef);

        updateProfileBadge();
        updateClock();
        showToast("Settings and profile saved!", "success");
    });

    document.getElementById("resetSettingsBtn").addEventListener("click", () => {
        if (!confirm("Reset all settings to defaults?")) return;
        localStorage.removeItem("nexusTheme");
        localStorage.removeItem("nexusUserName");
        localStorage.removeItem("nexusClockFormat");
        localStorage.removeItem("nexusVoiceDefault");

        applyTheme("purple");
        updateProfileBadge();
        updateClock();
        showSettings();
        showToast("Settings reset to defaults.", "info");
    });
}

function applyTheme(theme) {
    document.body.classList.remove("theme-purple", "theme-blue", "theme-green");
    document.body.classList.add("theme-" + theme);
    localStorage.setItem("nexusTheme", theme);
}

// Load saved theme when desktop starts
(function loadSavedTheme() {
    const savedTheme = localStorage.getItem("nexusTheme") || "purple";
    applyTheme(savedTheme);
})();

// =================================
// NEXUS CALCULATOR
// =================================

let calcCurrent = "0";
let calcPrevious = "";
let calcOp = null;
let calcResetOnNext = false;

function showCalculator() {
    const content = document.getElementById("windowContent");
    content.innerHTML = `
        <h3>🧮 NEXUS Calculator</h3>
        <div style="max-width:280px; margin:15px auto; background:#191228; padding:15px; border-radius:12px; border:1px solid #554477; box-shadow:0 4px 15px rgba(0,0,0,0.4);">
            <div id="calcExpr" style="min-height:18px; font-size:12px; color:#b9a6d5; text-align:right; padding:0 8px;"></div>
            <div id="calcDisplay" style="font-size:28px; font-weight:bold; color:white; text-align:right; padding:6px 8px; background:#100d20; border-radius:8px; margin-bottom:12px; overflow:hidden; text-overflow:ellipsis;">0</div>
            
            <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:8px;">
                <button class="nexus-btn calc-btn" onclick="calcAction('clear')" style="background:#553c7b;">AC</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('plusMinus')" style="background:#553c7b;">±</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('percent')" style="background:#553c7b;">%</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('op', '/')" style="background:#805ad5; font-size:16px;">÷</button>
                
                <button class="nexus-btn calc-btn" onclick="calcAction('digit', '7')">7</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('digit', '8')">8</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('digit', '9')">9</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('op', '*')" style="background:#805ad5; font-size:16px;">×</button>
                
                <button class="nexus-btn calc-btn" onclick="calcAction('digit', '4')">4</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('digit', '5')">5</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('digit', '6')">6</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('op', '-')" style="background:#805ad5; font-size:16px;">−</button>
                
                <button class="nexus-btn calc-btn" onclick="calcAction('digit', '1')">1</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('digit', '2')">2</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('digit', '3')">3</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('op', '+')" style="background:#805ad5; font-size:16px;">+</button>
                
                <button class="nexus-btn calc-btn" onclick="calcAction('digit', '0')" style="grid-column: span 2;">0</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('dot')">.</button>
                <button class="nexus-btn calc-btn" onclick="calcAction('equals')" style="background:#a855f7; font-weight:bold; font-size:18px;">=</button>
            </div>
        </div>
    `;
    updateCalcDisplay();
}

function updateCalcDisplay() {
    const disp = document.getElementById("calcDisplay");
    const expr = document.getElementById("calcExpr");
    if (!disp) return;
    disp.textContent = calcCurrent;
    if (expr) {
        expr.textContent = calcOp ? `${calcPrevious} ${calcOp === '*' ? '×' : calcOp === '/' ? '÷' : calcOp}` : '';
    }
}

function calcAction(type, val) {
    if (type === 'digit') {
        if (calcCurrent === '0' || calcResetOnNext) {
            calcCurrent = val;
            calcResetOnNext = false;
        } else {
            calcCurrent += val;
        }
    } else if (type === 'dot') {
        if (calcResetOnNext) {
            calcCurrent = '0.';
            calcResetOnNext = false;
        } else if (!calcCurrent.includes('.')) {
            calcCurrent += '.';
        }
    } else if (type === 'clear') {
        calcCurrent = '0';
        calcPrevious = '';
        calcOp = null;
        calcResetOnNext = false;
    } else if (type === 'plusMinus') {
        if (calcCurrent !== '0') {
            calcCurrent = calcCurrent.startsWith('-') ? calcCurrent.slice(1) : '-' + calcCurrent;
        }
    } else if (type === 'percent') {
        const num = parseFloat(calcCurrent);
        calcCurrent = String(num / 100);
    } else if (type === 'op') {
        if (calcOp && !calcResetOnNext) {
            calcCompute();
        }
        calcPrevious = calcCurrent;
        calcOp = val;
        calcResetOnNext = true;
    } else if (type === 'equals') {
        if (calcOp) {
            calcCompute();
            calcOp = null;
            calcResetOnNext = true;
        }
    }
    updateCalcDisplay();
}

function calcCompute() {
    const prev = parseFloat(calcPrevious);
    const curr = parseFloat(calcCurrent);
    if (isNaN(prev) || isNaN(curr)) return;
    let res = 0;
    if (calcOp === '+') res = prev + curr;
    else if (calcOp === '-') res = prev - curr;
    else if (calcOp === '*') res = prev * curr;
    else if (calcOp === '/') res = curr === 0 ? 'Error' : prev / curr;

    calcCurrent = (typeof res === 'number') ? String(Number(res.toFixed(8))) : String(res);
    calcPrevious = '';
}

// =================================
// NEXUS SYSTEM MONITOR
// =================================

function showSystemMonitor() {
    const content = document.getElementById("windowContent");
    content.innerHTML = `
        <h3>📊 NEXUS System Monitor</h3>
        <p style="color:#b9a6d5; font-size:12px; margin-bottom:14px;">Live health & resource telemetry of NEXUS AI OS.</p>
        
        <div id="sysMonitorContent" style="display:flex; flex-direction:column; gap:12px;">
            <em>Loading system telemetry...</em>
        </div>
        <div style="margin-top:14px; display:flex; gap:10px;">
            <button id="refreshSysBtn" class="nexus-btn">🔄 Refresh Metrics</button>
        </div>
    `;

    document.getElementById("refreshSysBtn").addEventListener("click", loadSystemTelemetry);
    loadSystemTelemetry();
}

function loadSystemTelemetry() {
    const container = document.getElementById("sysMonitorContent");
    if (!container) return;
    fetch("/api/system/info")
        .then(r => r.json())
        .then(info => {
            const counts = info.counts || {};
            const filesSizeKb = ((counts.files_size_bytes || 0) / 1024).toFixed(1);
            const dbSizeKb = ((info.database_size_bytes || 0) / 1024).toFixed(1);
            
            container.innerHTML = `
                <!-- Core Status Cards -->
                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:10px;">
                    <div style="background:#191228; padding:10px; border-radius:8px; border:1px solid #3d2b59; text-align:center;">
                        <span style="font-size:11px; color:#b9a6d5;">Core Status</span>
                        <div style="color:#48bb78; font-weight:bold; margin-top:4px;">🟢 ${escapeHtml(info.backend)}</div>
                    </div>
                    <div style="background:#191228; padding:10px; border-radius:8px; border:1px solid #3d2b59; text-align:center;">
                        <span style="font-size:11px; color:#b9a6d5;">Database</span>
                        <div style="color:#68d391; font-weight:bold; margin-top:4px;">🗄 ${escapeHtml(info.database)}</div>
                    </div>
                    <div style="background:#191228; padding:10px; border-radius:8px; border:1px solid #3d2b59; text-align:center;">
                        <span style="font-size:11px; color:#b9a6d5;">DB File Size</span>
                        <div style="color:#d8b4fe; font-weight:bold; margin-top:4px;">${dbSizeKb} KB</div>
                    </div>
                    <div style="background:#191228; padding:10px; border-radius:8px; border:1px solid #3d2b59; text-align:center;">
                        <span style="font-size:11px; color:#b9a6d5;">Python Runtime</span>
                        <div style="color:#f6ad55; font-weight:bold; margin-top:4px;">v${escapeHtml(info.python_version)}</div>
                    </div>
                </div>

                <!-- Database Metrics Breakdown -->
                <div style="background:#191228; padding:12px; border-radius:8px; border:1px solid #3d2b59;">
                    <h4 style="margin-bottom:8px; font-size:13px; color:#c4a5ff;">Persistent Storage Telemetry</h4>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:12px;">
                        <div>📝 Notes Created: <strong>${counts.notes || 0}</strong></div>
                        <div>💬 AI Conversations: <strong>${counts.conversations || 0}</strong></div>
                        <div>📋 Tasks Total: <strong>${counts.tasks || 0}</strong> (${counts.tasks_completed || 0} completed)</div>
                        <div>📅 Calendar Events: <strong>${counts.events || 0}</strong></div>
                        <div>📁 Uploaded Files: <strong>${counts.files || 0}</strong> (${filesSizeKb} KB)</div>
                        <div>🕒 Telemetry Timestamp: <strong>${new Date(info.time).toLocaleTimeString()}</strong></div>
                    </div>
                </div>

                <!-- Environment & Platform -->
                <div style="background:#191228; padding:10px 12px; border-radius:8px; border:1px solid #3d2b59; font-size:12px; color:#b9a6d5;">
                    🖥 Host OS: <span style="color:white;">${escapeHtml(info.platform)}</span>
                </div>
            `;
        })
        .catch(err => {
            container.innerHTML = `<span style="color:#ff5c7c;">Telemetry Error: ${err.message}</span>`;
        });
}

// =================================
// NEXUS APP LAUNCHER & KEYBOARD SHORTCUTS
// =================================

const OS_APPLICATIONS = [
    { name: "AI Assistant", icon: "🤖", desc: "Interactive Gemini AI chatbot & voice" },
    { name: "AI Agent Dashboard", icon: "⚡", desc: "Autonomous agent commands, multi-step actions & execution telemetry" },
    { name: "File Manager", icon: "📁", desc: "Persistent file storage, preview & download" },
    { name: "Notes", icon: "📝", desc: "Fast SQLite notes with instant search" },
    { name: "Task Manager", icon: "📋", desc: "Priorities, due dates & status metrics" },
    { name: "Calendar", icon: "📅", desc: "Event scheduling & monthly calendar" },
    { name: "Calculator", icon: "🧮", desc: "Arithmetic desktop calculator" },
    { name: "System Monitor", icon: "📊", desc: "Live health, DB & system telemetry" },
    { name: "Notification Center", icon: "🔔", desc: "System alerts and history" },
    { name: "Settings", icon: "⚙️", desc: "Themes, user profile & preferences" }
];

function toggleAppLauncher() {
    const modal = document.getElementById("appLauncherModal");
    if (!modal) return;
    const isHidden = modal.hidden;
    modal.hidden = !isHidden;
    if (!modal.hidden) {
        renderAppLauncher("");
        const search = document.getElementById("launcherSearchInput");
        if (search) {
            search.value = "";
            setTimeout(() => search.focus(), 60);
        }
    }
}

function renderAppLauncher(filterText = "") {
    const grid = document.getElementById("launcherAppsGrid");
    if (!grid) return;
    const query = filterText.toLowerCase().trim();
    const filtered = OS_APPLICATIONS.filter(app => 
        app.name.toLowerCase().includes(query) || app.desc.toLowerCase().includes(query)
    );

    grid.innerHTML = "";
    if (filtered.length === 0) {
        grid.innerHTML = "<p style='color:#a99ec2; grid-column:1/-1; text-align:center;'>No applications match your search.</p>";
        return;
    }

    filtered.forEach((app, idx) => {
        const item = document.createElement("div");
        item.className = "launcher-item";
        item.innerHTML = `
            <div class="launcher-icon">${app.icon}</div>
            <div class="launcher-title">${escapeHtml(app.name)}</div>
            <div class="launcher-desc">${escapeHtml(app.desc)}</div>
        `;
        item.onclick = () => {
            toggleAppLauncher();
            openApp(app.name);
        };
        grid.appendChild(item);
    });
}

// Bind App Launcher search input
document.addEventListener("DOMContentLoaded", () => {
    const search = document.getElementById("launcherSearchInput");
    if (search) {
        search.addEventListener("input", function() {
            renderAppLauncher(this.value);
        });
        search.addEventListener("keydown", function(e) {
            if (e.key === "Enter") {
                const query = this.value.toLowerCase().trim();
                const matched = OS_APPLICATIONS.find(app => 
                    app.name.toLowerCase().includes(query) || app.desc.toLowerCase().includes(query)
                );
                if (matched) {
                    toggleAppLauncher();
                    openApp(matched.name);
                }
            }
        });
    }
    const deskInput = document.getElementById("userInput");
    if (deskInput) {
        deskInput.addEventListener("keydown", function(e) {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }
    const deskLangSelect = document.getElementById("desktopVoiceLangSelect");
    if (deskLangSelect) {
        deskLangSelect.value = getSavedVoiceLanguage();
        deskLangSelect.addEventListener("change", function(e) {
            setSavedVoiceLanguage(e.target.value);
            const winSelect = document.getElementById("voiceLangSelect");
            if (winSelect) winSelect.value = e.target.value;
        });
    }
});

// Also bind immediately in case DOM is already loaded
(function initLauncherEvents() {
    const search = document.getElementById("launcherSearchInput");
    if (search) {
        search.addEventListener("input", function() {
            renderAppLauncher(this.value);
        });
        search.addEventListener("keydown", function(e) {
            if (e.key === "Enter") {
                const query = this.value.toLowerCase().trim();
                const matched = OS_APPLICATIONS.find(app => 
                    app.name.toLowerCase().includes(query) || app.desc.toLowerCase().includes(query)
                );
                if (matched) {
                    toggleAppLauncher();
                    openApp(matched.name);
                }
            }
        });
    }
})();

// Global Keyboard Shortcuts (Ctrl+Space, Alt+Space, Escape)
document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.altKey) && e.code === "Space") {
        e.preventDefault();
        toggleAppLauncher();
        return;
    }
    if (e.key === "Escape") {
        const launcher = document.getElementById("appLauncherModal");
        if (launcher && !launcher.hidden) {
            launcher.hidden = true;
            return;
        }
        const win = document.getElementById("appWindow");
        if (win && !win.hidden) {
            closeApp();
            return;
        }
    }
    const deskInput = document.getElementById("userInput");
    if (deskInput) {
        deskInput.addEventListener("keydown", function(e) {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }
    const deskLangSelect = document.getElementById("desktopVoiceLangSelect");
    if (deskLangSelect) {
        deskLangSelect.value = getSavedVoiceLanguage();
        deskLangSelect.addEventListener("change", function(e) {
            setSavedVoiceLanguage(e.target.value);
            const winSelect = document.getElementById("voiceLangSelect");
            if (winSelect) winSelect.value = e.target.value;
        });
    }
});

// =================================
// PHASE 5: AI AGENT DASHBOARD & AUTOMATION
// =================================

let lastPendingAgentCommand = null;

function showAgentDashboard() {
    const content = document.getElementById("windowContent");
    if (!content) return;

    content.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid #3d2b59; padding-bottom:8px;">
            <div style="display:flex; align-items:center; gap:8px;">
                <h2 style="margin:0; font-size:18px; color:#d8b4fe;">⚡ AI Agent Dashboard</h2>
                <span id="agentStatusBadge" style="background:#1e1430; border:1px solid #7c3aed; color:#c4b5fd; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:bold;">
                    Checking Agent Status...
                </span>
            </div>
            <button class="nexus-btn" onclick="refreshAgentDashboard()" style="padding:4px 10px; font-size:11px;">🔄 Refresh Telemetry</button>
        </div>

        <!-- Telemetry Metrics Cards -->
        <div id="agentMetricsCards" style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:10px; margin-bottom:14px;">
            <div style="background:#191228; padding:10px; border-radius:8px; border:1px solid #3d2b59; text-align:center;">
                <span style="font-size:11px; color:#b9a6d5;">Commands Run</span>
                <div id="metricTotalCommands" style="color:#d8b4fe; font-size:18px; font-weight:bold; margin-top:2px;">-</div>
            </div>
            <div style="background:#191228; padding:10px; border-radius:8px; border:1px solid #3d2b59; text-align:center;">
                <span style="font-size:11px; color:#b9a6d5;">Success Rate</span>
                <div id="metricSuccessRate" style="color:#4ade80; font-size:18px; font-weight:bold; margin-top:2px;">-</div>
            </div>
            <div style="background:#191228; padding:10px; border-radius:8px; border:1px solid #3d2b59; text-align:center;">
                <span style="font-size:11px; color:#b9a6d5;">Successful / Failed</span>
                <div id="metricSuccessFail" style="color:#60a5fa; font-size:18px; font-weight:bold; margin-top:2px;">-</div>
            </div>
            <div style="background:#191228; padding:10px; border-radius:8px; border:1px solid #3d2b59; text-align:center;">
                <span style="font-size:11px; color:#b9a6d5;">Confirmations</span>
                <div id="metricConfirmations" style="color:#fbbf24; font-size:18px; font-weight:bold; margin-top:2px;">-</div>
            </div>
        </div>

        <!-- Natural Language Command Runner -->
        <div style="background:#1e1430; border:1px solid #4a3470; border-radius:10px; padding:14px; margin-bottom:14px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <strong style="color:#e9d5ff; font-size:13px;">🎯 Execute Agent Command</strong>
                <span style="font-size:11px; color:#a99ec2;">Natural Language Intent & Multi-Step Planner</span>
            </div>

            <div style="display:flex; gap:8px; margin-bottom:10px;">
                <input type="text" id="agentCommandInput" class="nexus-input" placeholder="e.g. Schedule an event tomorrow at 3 PM, Create a note about my AI project..." style="flex:1; padding:8px 12px; font-size:13px;" />
                <button id="agentRunBtn" class="nexus-btn" onclick="runAgentCommandFromInput()" style="background:linear-gradient(135deg, #7c3aed, #9333ea); font-weight:bold; padding:8px 16px; border:none;">
                    ⚡ Execute
                </button>
            </div>

            <!-- Quick Action Suggestion Chips -->
            <div style="display:flex; flex-wrap:wrap; gap:6px; align-items:center;">
                <span style="font-size:11px; color:#a99ec2; margin-right:4px;">Quick Actions:</span>
                <button class="nexus-btn" style="font-size:10px; padding:3px 8px; border-radius:12px;" onclick="setAgentCommandAndRun('Create a note about my AI project.')">📝 AI Note</button>
                <button class="nexus-btn" style="font-size:10px; padding:3px 8px; border-radius:12px;" onclick="setAgentCommandAndRun('Add a high-priority task for tomorrow.')">📋 High-Priority Task</button>
                <button class="nexus-btn" style="font-size:10px; padding:3px 8px; border-radius:12px;" onclick="setAgentCommandAndRun('Schedule an event tomorrow at 3 PM.')">📅 Schedule 3 PM</button>
                <button class="nexus-btn" style="font-size:10px; padding:3px 8px; border-radius:12px;" onclick="setAgentCommandAndRun('Find my latest PDF and summarize it.')">📁 Summarize PDF</button>
                <button class="nexus-btn" style="font-size:10px; padding:3px 8px; border-radius:12px;" onclick="setAgentCommandAndRun('Show my pending tasks.')">🔍 Pending Tasks</button>
                <button class="nexus-btn" style="font-size:10px; padding:3px 8px; border-radius:12px;" onclick="setAgentCommandAndRun('Create a meeting note and schedule an event.')">⚡ Note & Calendar Workflow</button>
            </div>
        </div>

        <!-- Command Execution Live Progress / Result Box -->
        <div id="agentExecutionResultBox" style="display:none; background:#181126; border:1px solid #4a3470; border-radius:10px; padding:14px; margin-bottom:14px;">
            <div id="agentResultContent"></div>
        </div>

        <!-- Execution Logs & Activity History -->
        <div style="background:#191228; border:1px solid #3d2b59; border-radius:10px; padding:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <strong style="color:#d8b4fe; font-size:13px;">📋 Tool Execution & Activity History</strong>
                <span style="font-size:11px; color:#a99ec2;">SQLite Persistent Agent Audit Log</span>
            </div>
            <div id="agentLogsContainer" style="max-height:220px; overflow-y:auto;">
                <p style="color:#a99ec2; text-align:center; font-size:12px;">Loading activity logs...</p>
            </div>
        </div>
    `;

    // Bind Enter key in command input
    const input = document.getElementById("agentCommandInput");
    if (input) {
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") runAgentCommandFromInput();
        });
        setTimeout(() => input.focus(), 60);
    }

    refreshAgentDashboard();
}

function refreshAgentDashboard() {
    loadAgentStatus();
    loadAgentLogs();
}

function loadAgentStatus() {
    fetch("/api/agent/status")
        .then(r => r.json())
        .then(data => {
            const badge = document.getElementById("agentStatusBadge");
            if (badge) {
                if (data.agent_online) {
                    badge.style.background = "rgba(74, 222, 128, 0.15)";
                    badge.style.border = "1px solid #4ade80";
                    badge.style.color = "#4ade80";
                    badge.innerHTML = "🟢 AGENT ONLINE & OPERATIONAL";
                } else {
                    badge.style.background = "rgba(251, 191, 36, 0.15)";
                    badge.style.border = "1px solid #fbbf24";
                    badge.style.color = "#fbbf24";
                    badge.innerHTML = "🟡 OFFLINE FALLBACK ACTIVE";
                }
            }

            const m = data.metrics || {};
            const elTotal = document.getElementById("metricTotalCommands");
            const elRate = document.getElementById("metricSuccessRate");
            const elSF = document.getElementById("metricSuccessFail");
            const elConf = document.getElementById("metricConfirmations");

            if (elTotal) elTotal.textContent = m.total_commands || 0;
            if (elRate) elRate.textContent = m.success_rate || "100%";
            if (elSF) elSF.textContent = `${m.success_count || 0} / ${m.failed_count || 0}`;
            if (elConf) elConf.textContent = m.confirmation_count || 0;
        })
        .catch(err => {
            console.error("Agent status check error:", err);
        });
}

function loadAgentLogs() {
    const container = document.getElementById("agentLogsContainer");
    if (!container) return;

    fetch("/api/agent/logs?limit=25")
        .then(r => r.json())
        .then(logs => {
            if (!logs || logs.length === 0) {
                container.innerHTML = `<p style="color:#a99ec2; text-align:center; font-size:12px; margin:16px 0;">No command activities recorded yet. Run a command above!</p>`;
                return;
            }

            let html = `
                <table style="width:100%; border-collapse:collapse; font-size:11px; text-align:left;">
                    <thead>
                        <tr style="border-bottom:1px solid #3d2b59; color:#b9a6d5;">
                            <th style="padding:6px 8px;">Time</th>
                            <th style="padding:6px 8px;">Command</th>
                            <th style="padding:6px 8px;">Intent</th>
                            <th style="padding:6px 8px;">Tools Called</th>
                            <th style="padding:6px 8px;">Status</th>
                            <th style="padding:6px 8px;">Time</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            logs.forEach(log => {
                let statusBadge = "";
                if (log.status === "SUCCESS") {
                    statusBadge = `<span style="background:rgba(74, 222, 128, 0.15); color:#4ade80; border:1px solid #4ade80; padding:2px 6px; border-radius:4px; font-weight:bold;">SUCCESS</span>`;
                } else if (log.status === "CONFIRMATION_REQUIRED") {
                    statusBadge = `<span style="background:rgba(251, 191, 36, 0.15); color:#fbbf24; border:1px solid #fbbf24; padding:2px 6px; border-radius:4px; font-weight:bold;">CONFIRM</span>`;
                } else {
                    statusBadge = `<span style="background:rgba(239, 68, 68, 0.15); color:#ef4444; border:1px solid #ef4444; padding:2px 6px; border-radius:4px; font-weight:bold;">FAILED</span>`;
                }

                const timeStr = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : "";
                const toolsStr = Array.isArray(log.tools_called) ? log.tools_called.join(", ") : log.tools_called;

                html += `
                    <tr style="border-bottom:1px solid rgba(61,43,89,0.5);">
                        <td style="padding:6px 8px; color:#a99ec2; white-space:nowrap;">${timeStr}</td>
                        <td style="padding:6px 8px; color:#f3e8ff; font-weight:bold; max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(log.command)}">${escapeHtml(log.command)}</td>
                        <td style="padding:6px 8px;"><span style="background:#2a1c40; color:#c4b5fd; padding:1px 6px; border-radius:4px;">${escapeHtml(log.intent)}</span></td>
                        <td style="padding:6px 8px; color:#93c5fd; max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(toolsStr)}">${escapeHtml(toolsStr || "-")}</td>
                        <td style="padding:6px 8px;">${statusBadge}</td>
                        <td style="padding:6px 8px; color:#a99ec2;">${log.execution_time_ms || 0}ms</td>
                    </tr>
                `;
            });

            html += `</tbody></table>`;
            container.innerHTML = html;
        })
        .catch(err => {
            container.innerHTML = `<p style="color:#ef4444; font-size:12px;">Failed to load logs: ${err.message}</p>`;
        });
}

function setAgentCommandAndRun(cmd) {
    const input = document.getElementById("agentCommandInput");
    if (input) input.value = cmd;
    runAgentCommand(cmd);
}

function runAgentCommandFromInput() {
    const input = document.getElementById("agentCommandInput");
    if (!input) return;
    const cmd = input.value.trim();
    if (!cmd) {
        showToastNotification("⚠️ Please enter a command for the agent.");
        return;
    }
    runAgentCommand(cmd);
}

async function runAgentCommand(commandText, confirmed = false) {
    const box = document.getElementById("agentExecutionResultBox");
    const content = document.getElementById("agentResultContent");
    const runBtn = document.getElementById("agentRunBtn");

    if (box) box.style.display = "block";
    if (content) {
        content.innerHTML = `
            <div style="display:flex; align-items:center; gap:10px; color:#d8b4fe;">
                <div class="typing-indicator" style="padding:0; margin:0;"><span></span><span></span><span></span></div>
                <span>Agent is analyzing intent and executing multi-step workflow...</span>
            </div>
        `;
    }
    if (runBtn) {
        runBtn.disabled = true;
        runBtn.textContent = "⏳ Running...";
    }

    try {
        const res = await fetch("/api/agent/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command: commandText, confirmed: confirmed })
        });

        const data = await res.json();
        if (runBtn) {
            runBtn.disabled = false;
            runBtn.textContent = "⚡ Execute";
        }

        if (!res.ok) {
            throw new Error(data.error || "Agent execution failed.");
        }

        renderAgentExecutionResult(commandText, data);
        refreshAgentDashboard();

        // Handle desktop window actions
        if (data.client_actions && data.client_actions.length > 0) {
            handleClientActions(data.client_actions);
        }

    } catch (err) {
        if (runBtn) {
            runBtn.disabled = false;
            runBtn.textContent = "⚡ Execute";
        }
        if (content) {
            content.innerHTML = `
                <div style="color:#ef4444; padding:8px 12px; background:rgba(239, 68, 68, 0.1); border-left:3px solid #ef4444; border-radius:6px;">
                    <strong>❌ Execution Failed:</strong> ${escapeHtml(err.message)}
                </div>
            `;
        }
    }
}

function renderAgentExecutionResult(cmd, res) {
    const content = document.getElementById("agentResultContent");
    if (!content) return;

    lastPendingAgentCommand = cmd;

    // Check if safety confirmation is required
    if (res.status === "confirmation_required") {
        content.innerHTML = `
            <div style="background:rgba(251, 191, 36, 0.12); border:1px solid #fbbf24; border-radius:8px; padding:14px; margin-bottom:10px;">
                <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
                    <span style="font-size:18px;">⚠️</span>
                    <strong style="color:#fbbf24; font-size:14px;">Safety Confirmation Required</strong>
                </div>
                <p style="color:#fef3c7; font-size:13px; margin:0 0 12px 0;">${escapeHtml(res.confirmation_prompt || res.reply)}</p>
                <div style="display:flex; gap:10px;">
                    <button class="nexus-btn" style="background:#ef4444; border:none; padding:6px 14px; font-weight:bold;" onclick="runAgentCommand(lastPendingAgentCommand, true)">
                        ⚠️ Proceed & Permanently Delete
                    </button>
                    <button class="nexus-btn" style="padding:6px 14px;" onclick="cancelAgentAction()">
                        Cancel
                    </button>
                </div>
            </div>
        `;
        return;
    }

    // Normal multi-step or single-step execution result
    const intentBadge = `<span style="background:linear-gradient(135deg, #7c3aed, #a855f7); color:white; padding:3px 8px; border-radius:6px; font-size:11px; font-weight:bold;">${escapeHtml(res.intent || "GENERAL")}</span>`;
    const durationBadge = `<span style="color:#a99ec2; font-size:11px;">⏱ ${res.duration_ms || 0} ms</span>`;

    let stepsHtml = "";
    if (res.actions_executed && res.actions_executed.length > 0) {
        stepsHtml += `<div style="margin:10px 0; display:flex; flex-direction:column; gap:6px;">`;
        res.actions_executed.forEach(a => {
            const isError = a.result && a.result.error;
            const statusIcon = isError ? "❌" : "✅";
            const borderCol = isError ? "#ef4444" : "#4ade80";
            const msg = (a.result && a.result.message) || (a.result && a.result.error) || "Executed";

            stepsHtml += `
                <div style="background:#221838; border-left:3px solid ${borderCol}; padding:6px 10px; border-radius:4px; font-size:12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong>${statusIcon} Step ${a.step}: ${escapeHtml(a.description || a.tool)}</strong>
                        <code style="color:#c4b5fd; font-size:11px;">${escapeHtml(a.tool)}</code>
                    </div>
                    <div style="color:#e9d5ff; margin-top:2px; font-size:11px;">${escapeHtml(msg)}</div>
                </div>
            `;
        });
        stepsHtml += `</div>`;
    }

    const renderedReply = (typeof marked !== 'undefined') ? marked.parse(res.reply || "") : escapeHtml(res.reply || "");

    content.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; border-bottom:1px solid #3d2b59; padding-bottom:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:14px;">🎯</span>
                <strong style="color:#e9d5ff; font-size:13px;">Result for: "${escapeHtml(cmd)}"</strong>
                ${intentBadge}
            </div>
            ${durationBadge}
        </div>

        ${res.thought ? `<div style="font-size:11px; color:#c4b5fd; margin-bottom:8px; font-style:italic;">💭 Thought: ${escapeHtml(res.thought)}</div>` : ''}

        ${stepsHtml}

        <div style="background:#1f1633; padding:10px; border-radius:6px; font-size:13px; line-height:1.6; color:#f3e8ff; border:1px solid #3d2b59; margin-top:8px;">
            ${renderedReply}
        </div>
    `;
}

function cancelAgentAction() {
    const content = document.getElementById("agentResultContent");
    if (content) {
        content.innerHTML = `<div style="color:#a99ec2; font-size:12px;">Action was cancelled safely by user.</div>`;
    }
}

function handleClientActions(actions) {
    if (!actions || !Array.isArray(actions)) return;
    actions.forEach(act => {
        if (act.action === "open_app" && act.target) {
            showToastNotification(`🚀 Desktop Automation: Navigating to ${act.target}...`);
            setTimeout(() => {
                openApp(act.target);
            }, 600);
        }
    });
}
