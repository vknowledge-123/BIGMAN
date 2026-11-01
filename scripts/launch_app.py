"""Double-click entry point: reuse a running app or run one foreground server."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import threading
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
HOST, PORT = "127.0.0.1", 8000
URL = f"http://{HOST}:{PORT}"


def app_ready(url=URL):
    # Local traffic must not be sent through a configured corporate/web proxy.
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + "/openapi.json", timeout=1) as response:
            schema = json.load(response)
            info = schema.get("info") if isinstance(schema, dict) else None
            return isinstance(info, dict) and info.get("title") == "Dhan Turnover Scanner"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def open_dashboard(url=URL):
    print(f"Dashboard: {url}", flush=True)
    try:
        if not webbrowser.open(url, new=2):
            print("Open the dashboard address above in your browser.", flush=True)
    except Exception:
        print("Open the dashboard address above in your browser.", flush=True)


def open_when_ready(stopped, url=URL):
    attempts = 0
    while not stopped.is_set():
        if app_ready(url):
            if not stopped.is_set():
                open_dashboard(url)
            return
        attempts += 1
        if attempts == 30:
            print("Startup is taking longer than usual. See the server messages below; the browser will open when ready.", flush=True)
        stopped.wait(1)


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    print("Dhan Turnover Scanner", flush=True)
    print(f"App folder: {ROOT}", flush=True)
    # Claim the port before importing/starting the application, including when two
    # launchers are clicked together. Do not stop or replace another process.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind((HOST, PORT))
        listener.listen(128)
    except OSError:
        listener.close()
        for _ in range(5):
            if app_ready():
                print("The scanner is already running. Opening its dashboard.", flush=True)
                open_dashboard()
                return 0
            threading.Event().wait(1)
        print(f"Port {PORT} is already in use, but the scanner is not responding.")
        print("Check the existing Git Bash/server window. After safely stopping that server, double-click Start Scanner.bat again.")
        return 1
    stopped = threading.Event()
    try:
        if sys.version_info < (3, 10):
            print("Python 3.10 or newer is required.")
            return 1
        missing = [name for name in ("uvicorn", "fastapi", "pydantic", "dhanhq", "pandas", "requests")
                   if importlib.util.find_spec(name) is None]
        if missing:
            print("Missing Python packages: " + ", ".join(missing))
            print("Run this setup command once, then double-click the launcher again:")
            print(f'"{sys.executable}" -m pip install -r "{ROOT / "requirements.txt"}"')
            return 1
        import uvicorn
        print("Starting the app. Your browser will open when it is ready.", flush=True)
        print("Keep this window open while using the scanner or algos.", flush=True)
        print("To close the app: finish/exit active algos in the dashboard, then press Ctrl+C here.", flush=True)
        threading.Thread(target=open_when_ready, args=(stopped,), daemon=True).start()
        server = uvicorn.Server(uvicorn.Config("app.main:app", host=HOST, port=PORT, log_level="info"))
        server.run(sockets=[listener])
        return 0 if server.started else 1
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"Could not start the app: {exc}", flush=True)
        return 1
    finally:
        stopped.set()
        listener.close()


if __name__ == "__main__":
    raise SystemExit(main())
