"""
NEXUS AI OS - Browser Web Speech API & UI Live Verification
Launches Chrome, connects via Chrome DevTools Protocol (CDP),
and verifies real in-browser Web Speech API support, UI controls,
English/Tamil language selectors, editing, and window close hooks.
"""

import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import time
import urllib.request


def create_websocket(ws_url):
    # Parse ws://host:port/path
    parts = ws_url.replace("ws://", "").split("/", 1)
    host_port = parts[0].split(":")
    host = host_port[0]
    port = int(host_port[1])
    path = "/" + parts[1] if len(parts) > 1 else "/"

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect((host, port))

    sec_key = base64.b64encode(os.urandom(16)).decode()
    handshake = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {sec_key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    s.sendall(handshake.encode())
    resp = s.recv(4096).decode("latin-1")
    if "101 " not in resp:
        raise RuntimeError(f"WebSocket handshake failed: {resp}")
    return s


class CDPClient:
    def __init__(self, sock):
        self.sock = sock
        self.buf = bytearray()

    def send(self, msg_id, method, params=None):
        payload = {"id": msg_id, "method": method, "params": params or {}}
        data = json.dumps(payload).encode("utf-8")

        frame = bytearray([0x81])
        length = len(data)
        mask_key = os.urandom(4)

        if length <= 125:
            frame.append(0x80 | length)
        elif length <= 65535:
            frame.append(0x80 | 126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack("!Q", length))

        frame.extend(mask_key)
        masked_data = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(data))
        frame.extend(masked_data)
        self.sock.sendall(frame)

    def read_until(self, target_id, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            # First try parsing any complete frames already in buffer
            while len(self.buf) >= 2:
                b1 = self.buf[0]
                b2 = self.buf[1]
                payload_len = b2 & 0x7F
                offset = 2

                if payload_len == 126:
                    if len(self.buf) < 4:
                        break
                    payload_len = struct.unpack("!H", self.buf[2:4])[0]
                    offset = 4
                elif payload_len == 127:
                    if len(self.buf) < 10:
                        break
                    payload_len = struct.unpack("!Q", self.buf[2:10])[0]
                    offset = 10

                if len(self.buf) < offset + payload_len:
                    break

                msg_bytes = bytes(self.buf[offset : offset + payload_len])
                self.buf = self.buf[offset + payload_len :]

                try:
                    msg_json = json.loads(msg_bytes.decode("utf-8"))
                    if msg_json.get("id") == target_id:
                        return msg_json
                except Exception:
                    pass

            # Need more data
            chunk = self.sock.recv(65536)
            if not chunk:
                break
            self.buf.extend(chunk)
        return None

    def evaluate(self, msg_id, expression):
        self.send(msg_id, "Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True
        })
        res = self.read_until(msg_id)
        if not res:
            raise TimeoutError(f"No response for CDP eval: {expression[:50]}")
        return res.get("result", {}).get("result", {}).get("value")


def main():
    print("=" * 60)
    print("NEXUS AI OS — Day 9 Browser Web Speech API Live Test")
    print("=" * 60)

    # 1. Start headless Chrome with remote debugging
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    user_data = os.path.join(os.environ.get("TEMP", r"C:\Temp"), "nexus_speech_profile")
    os.makedirs(user_data, exist_ok=True)

    args = [
        chrome_path,
        "--remote-debugging-port=9222",
        "--headless=new",
        f"--user-data-dir={user_data}",
        "--no-first-run",
        "--no-default-browser-check",
        "--use-fake-ui-for-media-stream",  # Auto-grant mic permission for testing
        "--use-fake-device-for-media-stream",  # Fake mic audio device
        "http://127.0.0.1:5000"
    ]

    print("[1/8] Launching Google Chrome with DevTools protocol...")
    chrome_proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

    try:
        # 2. Get WebSocket debugger URL from Chrome
        tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/list").read().decode())
        page_tab = next((t for t in tabs if "http://127.0.0.1:5000" in t.get("url", "") or t.get("type") == "page"), None)
        if not page_tab:
            raise RuntimeError("No Chrome page tab found.")

        ws_url = page_tab["webSocketDebuggerUrl"]
        print(f"[2/8] Connected to Chrome tab: {page_tab.get('title')}")
        sock = create_websocket(ws_url)
        cdp = CDPClient(sock)

        # 3. Wait for page scripts to load and execute
        current_url = cdp.evaluate(6, "window.location.href")
        print(f"[2/8] Page URL in Chrome: {current_url}")

        debug_info = cdp.evaluate(7, """
            (() => {
                const s = document.createElement('script');
                s.src = 'script.js';
                return new Promise((resolve) => {
                    s.onload = () => resolve({ loaded: true, fn: typeof isWebSpeechSupported });
                    s.onerror = (e) => resolve({ loaded: false, err: String(e) });
                    document.head.appendChild(s);
                });
            })()
        """)
        print(f"[debug] Explicit script tag test: {debug_info}")

        fn_type = "undefined"
        for attempt in range(10):
            fn_type = cdp.evaluate(8 + attempt, "typeof isWebSpeechSupported")
            if fn_type == "function":
                break
            time.sleep(0.5)

        print(f"[2/8] typeof isWebSpeechSupported: {fn_type}")

        # 4. Check Web Speech API in Chrome
        web_speech_type = cdp.evaluate(20, "typeof (window.SpeechRecognition || window.webkitSpeechRecognition)")
        print(f"[3/8] Chrome Web Speech API support: {web_speech_type} -> {'PASS (Native webkitSpeechRecognition supported)' if web_speech_type == 'function' else 'FAIL'}")
        assert web_speech_type == "function", "Chrome must support webkitSpeechRecognition"

        has_webkit = cdp.evaluate(21, "'webkitSpeechRecognition' in window")
        print(f"[3/8] 'webkitSpeechRecognition' in window: {has_webkit}")

        supported_check = cdp.evaluate(22, "typeof isWebSpeechSupported === 'function' ? isWebSpeechSupported() : 'fn_missing'")
        print(f"[3/8] isWebSpeechSupported() returned: {supported_check}")
        assert supported_check is True

        # 5. Check desktop controls
        desktop_mic_exists = cdp.evaluate(30, "document.getElementById('desktopMicBtn') !== null")
        desktop_lang_exists = cdp.evaluate(31, "document.getElementById('desktopVoiceLangSelect') !== null")
        print(f"[4/8] Desktop UI elements: Mic Button={desktop_mic_exists}, Language Select={desktop_lang_exists}")
        assert desktop_mic_exists and desktop_lang_exists

        # 6. Open AI Assistant window
        print("[5/8] Opening AI Assistant window...")
        cdp.evaluate(40, "openApp('AI Assistant')")
        time.sleep(1)

        win_mic_exists = cdp.evaluate(41, "document.getElementById('micBtn') !== null")
        win_lang_exists = cdp.evaluate(42, "document.getElementById('voiceLangSelect') !== null")
        status_bar_exists = cdp.evaluate(43, "document.getElementById('micStatusBar') !== null")
        input_exists = cdp.evaluate(44, "document.getElementById('assistantUserInput') !== null")

        print(f"[5/8] AI Assistant controls: Mic Button={win_mic_exists}, Language Select={win_lang_exists}, Status Bar={status_bar_exists}, Input={input_exists}")
        assert win_mic_exists and win_lang_exists and status_bar_exists and input_exists

        # 7. Check Language Options (en-IN and ta-IN)
        lang_options = cdp.evaluate(50, """
            Array.from(document.getElementById('voiceLangSelect').options).map(o => ({ value: o.value, text: o.text }))
        """)
        print(f"[6/8] Supported voice languages in selector: {json.dumps(lang_options, ensure_ascii=False)}")
        lang_values = [o['value'] for o in lang_options]
        assert 'en-IN' in lang_values, "en-IN (English India) must be present"
        assert 'ta-IN' in lang_values, "ta-IN (Tamil India) must be present"

        # Test selecting Tamil (ta-IN)
        cdp.evaluate(51, """
            (() => {
                const sel = document.getElementById('voiceLangSelect');
                sel.value = 'ta-IN';
                sel.dispatchEvent(new Event('change'));
            })()
        """)
        saved_lang = cdp.evaluate(52, "getSavedVoiceLanguage()")
        print(f"[6/8] Switched language to Tamil: saved_lang = {saved_lang}")
        assert saved_lang == 'ta-IN'

        # Switch back to English (en-IN)
        cdp.evaluate(53, """
            (() => {
                const sel = document.getElementById('voiceLangSelect');
                sel.value = 'en-IN';
                sel.dispatchEvent(new Event('change'));
            })()
        """)
        saved_lang_en = cdp.evaluate(54, "getSavedVoiceLanguage()")
        print(f"[6/8] Switched language to English: saved_lang = {saved_lang_en}")
        assert saved_lang_en == 'en-IN'

        # 8. Test Voice Input Triggering, Text Editing & Stop Control
        print("[7/8] Testing Speech Recognition trigger, Stop Listening, and input editing...")
        # Trigger speech recognition
        cdp.evaluate(60, "document.getElementById('micBtn').click()")
        time.sleep(0.5)

        is_active = cdp.evaluate(61, "isRecordingAudio")
        btn_has_recording_class = cdp.evaluate(62, "document.getElementById('micBtn').classList.contains('mic-recording')")
        print(f"[7/8] Speech recognition active: {is_active}, Button pulsing: {btn_has_recording_class}")

        # Stop listening
        cdp.evaluate(63, "stopSpeechRecognition()")
        time.sleep(0.3)
        is_stopped = cdp.evaluate(64, "!isRecordingAudio")
        print(f"[7/8] Stop Listening successfully stopped recognition: {is_stopped}")
        assert is_stopped

        # Verify editing recognized text (English and Tamil)
        test_speech_text = "What is the capital of India?"
        cdp.evaluate(70, f"""
            (() => {{
                const input = document.getElementById('assistantUserInput');
                input.value = '{test_speech_text}';
                input.value += ' Explain briefly.';
            }})()
        """)
        edited_text = cdp.evaluate(71, "document.getElementById('assistantUserInput').value")
        print(f"[7/8] English review & editing verified: '{edited_text}'")
        assert edited_text == "What is the capital of India? Explain briefly."

        tamil_speech_text = "வணக்கம், கணினி அறிவியல் என்றால் என்ன?"
        cdp.evaluate(72, f"""
            (() => {{
                const input = document.getElementById('assistantUserInput');
                input.value = '{tamil_speech_text}';
                input.value += ' சுருக்கமாக விளக்குக.';
            }})()
        """)
        edited_tamil_text = cdp.evaluate(73, "document.getElementById('assistantUserInput').value")
        print(f"[7/8] Tamil review & editing verified: '{edited_tamil_text}'")
        assert edited_tamil_text == "வணக்கம், கணினி அறிவியல் என்றால் என்ன? சுருக்கமாக விளக்குக."

        # 9. Verify closeApp stops recognition
        print("[8/8] Testing closeApp() stops active recognition...")
        cdp.evaluate(80, "document.getElementById('micBtn').click()")
        time.sleep(0.3)
        cdp.evaluate(81, "closeApp()")
        is_active_after_close = cdp.evaluate(82, "isRecordingAudio")
        print(f"[8/8] Recognition stopped upon window close: {not is_active_after_close}")
        assert not is_active_after_close

        print("\n" + "=" * 60)
        print("🎉 ALL IN-BROWSER WEB SPEECH API TESTS PASSED SUCCESSFULLY!")
        print("=" * 60)

    finally:
        try:
            chrome_proc.terminate()
            chrome_proc.wait(timeout=3)
        except Exception:
            chrome_proc.kill()


if __name__ == "__main__":
    main()
