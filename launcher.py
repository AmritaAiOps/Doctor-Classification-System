"""Desktop-app entrypoint: start the FastAPI server (which also serves the
built React UI) on a local port, then show it in a native window via
pywebview. Closing the window quits the app. Fully offline -- no internet.
"""
import socket
import threading
import time
import traceback
import webbrowser

import uvicorn
import webview

from backend.main import app
from backend.runtime_paths import ROOT

HOST = "127.0.0.1"


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def wait_until_up(port, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex((HOST, port)) == 0:
                return
        time.sleep(0.15)


class Api:
    """Exposed to the frontend as window.pywebview.api.* -- lets the web UI
    trigger native OS dialogs (a browser alone can't pick a folder)."""

    def choose_folder(self):
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None


def main():
    port = find_free_port()
    threading.Thread(
        target=lambda: uvicorn.run(app, host=HOST, port=port, log_level="warning"),
        daemon=True,
    ).start()
    wait_until_up(port)
    url = f"http://{HOST}:{port}"
    try:
        webview.create_window("Daily HIS Report", url, width=1280, height=860, js_api=Api())
        webview.start()  # blocks until the window is closed
    except Exception:
        # Native window needs the WebView2 runtime (present on Win11 and nearly
        # all Win10). If it's missing, don't crash -- fall back to the browser.
        webbrowser.open(url)
        threading.Event().wait()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # No console in a windowed build -- leave a breadcrumb if startup dies.
        ROOT.mkdir(parents=True, exist_ok=True)
        (ROOT / "startup_error.log").write_text(traceback.format_exc())
        raise
