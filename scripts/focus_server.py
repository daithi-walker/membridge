#!/usr/bin/env python3
"""
Tiny host-side HTTP server for iTerm2 tab management.
Runs on localhost:7843 — separate from the Docker container because
osascript must execute on the Mac host, not inside a Linux container.

Endpoints:
  POST /focus   {"session_id": "...", "pid": 12345}
                Focus strategy (in order):
                1. Match by PID → TTY → iTerm2 session (reliable)
                2. Fall back to opening a new tab with claude --resume <id>

  POST /rename  {"old_name": "bash", "new_name": "alembic · feat/branch"}
                Renames the first iTerm2 session whose name contains old_name.

  GET  /sessions
                Lists all iTerm2 session names (debug).

  GET  /pid/<pid>
                Returns {"alive": true/false} — whether the PID is still running on the host.

  POST /sync-tabs
                Runs sync_iterm_tabs.py in the background (non-blocking).
                Returns immediately with {"ok": true, "status": "started"}.
                The dashboard should re-fetch /api/sessions after ~35s.
"""

import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_SYNC_SCRIPT = os.path.join(os.path.dirname(__file__), "sync_iterm_tabs.py")

PORT = 7843

# Locate claude binary at startup — new iTerm2 tabs have a restricted PATH
_CLAUDE_BIN = (
    shutil.which("claude")
    or os.path.expanduser("~/.local/bin/claude")
)

_FOCUS_BY_TTY_SCRIPT = """
tell application "iTerm2"
    set targetTty to "{tty}"
    repeat with w in windows
        repeat with t in tabs of w
            repeat with s in sessions of t
                try
                    -- iTerm2 tty includes /dev/ prefix; ps output does not
                    set sTty to tty of s
                    if sTty ends with targetTty then
                        select w
                        select t
                        return "focused"
                    end if
                end try
            end repeat
        end repeat
    end repeat
    return "not_found"
end tell
"""

_OPEN_TAB_SCRIPT = """
tell application "iTerm2"
    tell current window
        create tab with default profile command "bash -c 'cd {cwd} && {claude_bin} --resume {session_id}'"
    end tell
    return "opened"
end tell
"""

_RENAME_SCRIPT = """
tell application "iTerm2"
    set matchName to "{old_name}"
    set newName to "{new_name}"
    repeat with w in windows
        repeat with t in tabs of w
            repeat with s in sessions of t
                if name of s contains matchName then
                    set name of s to newName
                    return "renamed"
                end if
            end repeat
        end repeat
    end repeat
    return "not_found"
end tell
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/sessions":
            self._handle_list_sessions()
        elif self.path.startswith("/pid/"):
            self._handle_pid_check(self.path[5:])
        else:
            self._respond(404, {"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://localhost:7842")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle_pid_check(self, pid_str: str):
        try:
            pid = int(pid_str)
            os.kill(pid, 0)  # signal 0 = existence check, no actual signal
            self._respond(200, {"alive": True})
        except ValueError:
            self._respond(400, {"error": "invalid pid"})
        except ProcessLookupError:
            self._respond(200, {"alive": False})
        except PermissionError:
            # Process exists but we can't signal it — still alive
            self._respond(200, {"alive": True})

    def _handle_list_sessions(self):
        script = """
tell application "iTerm2"
  set output to {}
  repeat with w in windows
    set tabIndex to 1
    repeat with t in tabs of w
      repeat with s in sessions of t
        set end of output to name of s
      end repeat
      set tabIndex to tabIndex + 1
    end repeat
  end repeat
  return output
end tell
"""
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5
            )
            names = [n.strip() for n in result.stdout.strip().split(",") if n.strip()]
            self._respond(200, {"sessions": names, "count": len(names)})
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")

        if self.path == "/focus":
            self._handle_focus(body)
        elif self.path == "/rename":
            self._handle_rename(body)
        elif self.path == "/sync-tabs":
            self._handle_sync_tabs()
        else:
            self._respond(404, {"error": "not found"})

    def _handle_focus(self, body):
        session_id = body.get("session_id", "")
        pid = body.get("pid")
        cwd = body.get("cwd") or os.path.expanduser("~")
        if not session_id:
            self._respond(400, {"error": "session_id required"})
            return

        # Strategy 1: find iTerm2 session by PID → TTY
        if pid:
            tty = self._pid_to_tty(int(pid))
            if tty:
                script = _FOCUS_BY_TTY_SCRIPT.format(tty=tty.replace('"', '\\"'))
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True, text=True, timeout=5
                )
                action = result.stdout.strip()
                if action == "focused":
                    self._respond(200, {"ok": True, "action": "focused"})
                    return

        # Strategy 2: open a new tab with claude --resume, cd to session's cwd first
        script = _OPEN_TAB_SCRIPT.format(
            cwd=cwd.replace('"', '\\"'),
            claude_bin=_CLAUDE_BIN.replace('"', '\\"'),
            session_id=session_id.replace('"', '\\"'),
        )
        self._run_osascript(script, default_action="opened")

    @staticmethod
    def _pid_to_tty(pid: int) -> str | None:
        try:
            result = subprocess.run(
                ["ps", "-o", "tty=", "-p", str(pid)],
                capture_output=True, text=True, timeout=3
            )
            tty = result.stdout.strip()
            return tty if tty and tty != "??" else None
        except Exception:
            return None

    def _handle_sync_tabs(self):
        iterm2_python = os.environ.get("ITERM2_PYTHON", "")

        def _run():
            cmd = [sys.executable, _SYNC_SCRIPT]
            if iterm2_python:
                cmd = [iterm2_python, _SYNC_SCRIPT]
            subprocess.run(cmd, capture_output=True, timeout=60)

        threading.Thread(target=_run, daemon=True).start()
        self._respond(200, {"ok": True, "status": "started", "eta_secs": 35})

    def _handle_rename(self, body):
        old_name = body.get("old_name", "")
        new_name = body.get("new_name", "")
        if not old_name or not new_name:
            self._respond(400, {"error": "old_name and new_name required"})
            return
        script = _RENAME_SCRIPT.format(
            old_name=old_name.replace('"', '\\"'),
            new_name=new_name.replace('"', '\\"'),
        )
        self._run_osascript(script)

    def _run_osascript(self, script, default_action="ok"):
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5
            )
            action = result.stdout.strip() or default_action
            self._respond(200, {"ok": True, "action": action})
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _respond(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(data))
        self.send_header("Access-Control-Allow-Origin", "http://localhost:7842")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Focus server listening on http://127.0.0.1:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
