import subprocess
import time
import requests
import os
import shutil
import tempfile

def test_compiled_backend():
    exe_path = os.path.abspath("build/backend/nexus_backend/nexus_backend.exe")
    assert os.path.isfile(exe_path), f"Executable not found at {exe_path}"
    print(f"Testing compiled executable: {exe_path}")

    temp_data_dir = tempfile.mkdtemp(prefix="nexus_test_data_")
    test_port = "5055"
    test_url = f"http://127.0.0.1:{test_port}"

    env = os.environ.copy()
    env["PORT"] = test_port
    env["NEXUS_DATA_DIR"] = temp_data_dir
    env["FLASK_ENV"] = "production"

    print(f"Launching process on port {test_port} with NEXUS_DATA_DIR={temp_data_dir}...")
    proc = subprocess.Popen([exe_path], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    try:
        # Poll /api/status
        started = False
        for attempt in range(40):
            time.sleep(0.5)
            try:
                res = requests.get(f"{test_url}/api/status", timeout=1)
                if res.status_code == 200:
                    data = res.json()
                    print(f"SUCCESS: Backend online at {test_url} after {attempt + 1} attempts!")
                    print(f"Status Payload: {data}")
                    assert data.get("system") == "NEXUS AI OS"
                    assert data.get("backend") == "Running"
                    assert data.get("database") == "Connected"
                    started = True
                    break
            except Exception:
                pass

        if not started:
            stdout, stderr = proc.communicate(timeout=3)
            print("Process stdout:", stdout.decode(errors="replace"))
            print("Process stderr:", stderr.decode(errors="replace"))
            assert started, "Compiled backend failed to respond within timeout!"

        # Test static file serving from bundled assets
        res_home = requests.get(test_url, timeout=2)
        assert res_home.status_code == 200
        assert "NEXUS AI OS" in res_home.text
        print("SUCCESS: Frontend HTML served from packaged binary!")

        # Request graceful shutdown
        print("Sending graceful shutdown request...")
        res_shutdown = requests.post(f"{test_url}/api/shutdown", timeout=2)
        assert res_shutdown.status_code == 200
        print("SUCCESS: Shutdown signal accepted!")

        proc.wait(timeout=5)
        print(f"SUCCESS: Backend process terminated cleanly with code {proc.returncode}!")

    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            shutil.rmtree(temp_data_dir, ignore_errors=True)
        except Exception:
            pass

if __name__ == "__main__":
    test_compiled_backend()
