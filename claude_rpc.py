"""Claude RPC - shows your Claude Code activity as Discord Rich Presence."""
import json
import os
import struct
import sys
import threading
import time
import uuid
import webbrowser
import winreg
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pystray
from PIL import Image

APP_NAME = "ClaudeRPC"
LOGO_URL = "https://raw.githubusercontent.com/izzyfrm/claude-rpc/main/assets/logo.png"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "claude-rpc"
CONFIG_PATH = CONFIG_DIR / "config.json"
SETTINGS_PORT = 47823

DEFAULTS = {
    "client_id": "",
    "enabled": True,
    "show_model": True,
    "show_chat": True,
    "chat_source": "title",  # "title" or "prompt"
    "show_project": True,
    "show_timer": True,
    "idle_minutes": 10,
    "large_image": LOGO_URL,
    "large_text": "Claude Code",
    "button_label": "",
    "button_url": "",
    "start_with_windows": False,
}


def resource(name):
    base = getattr(sys, "_MEIPASS", Path(__file__).parent)
    return Path(base) / name


# ---------------------------------------------------------------- config

class Config:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = dict(DEFAULTS)
        try:
            self.data.update(json.loads(CONFIG_PATH.read_text("utf-8")))
        except (OSError, ValueError):
            pass

    def get(self):
        with self.lock:
            return dict(self.data)

    def update(self, new):
        with self.lock:
            for k, v in new.items():
                if k in DEFAULTS:
                    self.data[k] = type(DEFAULTS[k])(v)
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(json.dumps(self.data, indent=2), "utf-8")
        set_autostart(self.data["start_with_windows"])


def set_autostart(enabled):
    if not getattr(sys, "frozen", False):
        return
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
    try:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}"')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


# ---------------------------------------------------------------- discord ipc

class DiscordIPC:
    """Minimal Discord RPC client over the local named pipe."""

    def __init__(self):
        self.pipe = None
        self.client_id = None

    def connect(self, client_id):
        self.close()
        for i in range(10):
            try:
                self.pipe = open(rf"\\?\pipe\discord-ipc-{i}", "r+b", buffering=0)
                break
            except OSError:
                continue
        else:
            return False
        try:
            self._send(0, {"v": 1, "client_id": client_id})
            op, data = self._recv()
            if data.get("evt") != "READY":
                raise OSError(data.get("message", "handshake failed"))
        except OSError:
            self.close()
            return False
        self.client_id = client_id
        return True

    def _send(self, op, payload):
        body = json.dumps(payload).encode()
        self.pipe.write(struct.pack("<II", op, len(body)) + body)

    def _recv(self):
        op, length = struct.unpack("<II", self.pipe.read(8))
        return op, json.loads(self.pipe.read(length))

    def set_activity(self, activity):
        self._send(1, {"cmd": "SET_ACTIVITY", "nonce": str(uuid.uuid4()),
                       "args": {"pid": os.getpid(), "activity": activity}})
        self._recv()

    def close(self):
        if self.pipe:
            try:
                self.pipe.close()
            except OSError:
                pass
        self.pipe = None
        self.client_id = None


# ---------------------------------------------------------------- claude sessions

def pretty_model(model_id):
    if not model_id or model_id.startswith("<"):
        return None
    parts = model_id.removeprefix("claude-").split("-")
    parts = [p for p in parts if not (p.isdigit() and len(p) == 8)]  # drop date stamps
    name = [p for p in parts if not p.isdigit()]
    ver = [p for p in parts if p.isdigit()]
    return " ".join(n.capitalize() for n in name) + (" " + ".".join(ver) if ver else "")


def text_of(content):
    if isinstance(content, str):
        return content
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text", "")
    return ""


def latest_session():
    """Return info about the most recently active Claude Code session, or None."""
    try:
        files = [f for f in PROJECTS_DIR.glob("*/*.jsonl")]
    except OSError:
        return None
    if not files:
        return None
    path = max(files, key=lambda f: f.stat().st_mtime)
    info = {"mtime": path.stat().st_mtime, "model": None, "title": None, "prompt": None, "project": None, "start": None}
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if '"type":"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                t = e.get("type")
                if info["start"] is None and e.get("timestamp"):
                    info["start"] = e["timestamp"]
                if e.get("cwd"):
                    info["project"] = Path(e["cwd"]).name
                if t == "custom-title" and e.get("customTitle"):
                    info["title"] = e["customTitle"]
                elif t == "summary" and e.get("summary") and not info["title"]:
                    info["title"] = e["summary"]
                elif t == "assistant":
                    m = pretty_model(e.get("message", {}).get("model"))
                    if m:
                        info["model"] = m
                elif t == "user" and not e.get("isMeta") and not e.get("isSidechain"):
                    txt = text_of(e.get("message", {}).get("content")).strip()
                    if txt and not txt.startswith("<"):
                        info["prompt"] = txt
    except OSError:
        return None
    return info


def iso_to_epoch(ts):
    from datetime import datetime
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
    except (ValueError, AttributeError):
        return None


def clip(s, n=128):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def build_activity(cfg, s):
    chat = s["title"] or s["prompt"]
    if cfg["chat_source"] == "prompt":
        chat = s["prompt"] or s["title"]
    details = clip(chat) if cfg["show_chat"] and chat else "Coding with Claude"
    bits = []
    if cfg["show_model"] and s["model"]:
        bits.append(s["model"])
    if cfg["show_project"] and s["project"]:
        bits.append(s["project"])
    act = {"details": details, "assets": {"large_image": cfg["large_image"] or LOGO_URL,
                                          "large_text": cfg["large_text"] or "Claude Code"}}
    if bits:
        act["state"] = clip(" · ".join(bits))
    if cfg["show_timer"] and s["start"]:
        start = iso_to_epoch(s["start"])
        if start:
            act["timestamps"] = {"start": start}
    if cfg["button_label"] and cfg["button_url"].startswith("http"):
        act["buttons"] = [{"label": clip(cfg["button_label"], 32), "url": cfg["button_url"]}]
    return act


# ---------------------------------------------------------------- presence loop

class Presence:
    def __init__(self, config):
        self.config = config
        self.ipc = DiscordIPC()
        self.status = "Starting"
        self.current = None
        self.last_sent = None
        self.wake = threading.Event()

    def run(self):
        while True:
            try:
                self.tick()
            except (OSError, struct.error, ValueError):
                self.ipc.close()
                self.last_sent = None
                self.status = "Lost connection to Discord, retrying"
            self.wake.wait(5)
            self.wake.clear()

    def tick(self):
        cfg = self.config.get()
        if not cfg["client_id"].strip():
            self.status = "Add your Discord Application ID in Settings"
            return
        if self.ipc.client_id != cfg["client_id"].strip():
            if not self.ipc.connect(cfg["client_id"].strip()):
                self.status = "Waiting for Discord"
                return
            self.last_sent = None
        s = latest_session()
        active = cfg["enabled"] and s and time.time() - s["mtime"] < cfg["idle_minutes"] * 60
        activity = build_activity(cfg, s) if active else None
        self.current = activity
        if activity != self.last_sent:
            self.ipc.set_activity(activity)
            self.last_sent = activity
        self.status = "Showing on Discord" if activity else ("Paused" if not cfg["enabled"] else "Idle, no recent Claude session")


# ---------------------------------------------------------------- settings server

def make_handler(config, presence):
    page = resource("settings.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(page)
            elif self.path == "/api/config":
                self._json(config.get())
            elif self.path == "/api/status":
                self._json({"status": presence.status, "activity": presence.current})
            else:
                self.send_error(404)

        def do_POST(self):
            # Only accept same-origin requests from the settings page.
            if self.headers.get("Origin") not in (None, f"http://127.0.0.1:{SETTINGS_PORT}"):
                return self.send_error(403)
            if self.path != "/api/config":
                return self.send_error(404)
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                config.update(data)
            except (ValueError, TypeError) as e:
                return self._json({"error": str(e)}, 400)
            presence.wake.set()
            self._json(config.get())

    return Handler


def open_settings():
    webbrowser.open(f"http://127.0.0.1:{SETTINGS_PORT}/")


def main():
    config = Config()
    presence = Presence(config)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", SETTINGS_PORT), make_handler(config, presence))
    except OSError:
        open_settings()  # already running: just show its settings
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=presence.run, daemon=True).start()
    if not config.get()["client_id"]:
        open_settings()

    def toggle(icon, item):
        config.update({"enabled": not config.get()["enabled"]})
        presence.wake.set()

    menu = pystray.Menu(
        pystray.MenuItem(lambda i: presence.status, None, enabled=False),
        pystray.MenuItem("Settings", lambda: open_settings(), default=True),
        pystray.MenuItem("Enabled", toggle, checked=lambda i: config.get()["enabled"]),
        pystray.MenuItem("Quit", lambda icon: icon.stop()),
    )
    pystray.Icon(APP_NAME, Image.open(resource("assets/logo.ico")), "Claude RPC", menu).run()
    try:
        presence.ipc.close()
    finally:
        os._exit(0)


if __name__ == "__main__":
    main()
