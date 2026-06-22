#!/usr/bin/env python3
"""
Tiny host-side HTTP server for iTerm2 tab management.
Runs on localhost:7843 — separate from the Docker container because
osascript must execute on the Mac host, not inside a Linux container.

Endpoints:
  POST /focus   {"session_id": "abc...", "tab": "my-project"}
                Focuses the iTerm2 tab whose name contains `tab`.
                Falls back to opening a new tab with `claude --resume <id>`.

  POST /rename  {"old_name": "bash", "new_name": "alembic · feat/ALGDE-99"}
                Renames the first iTerm2 tab whose name contains `old_name`.
                Called by the heartbeat hook on first registration.
"""

import json
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 7843

# Locate claude binary at startup — new iTerm2 tabs inherit a restricted PATH
_CLAUDE_BIN = (
    shutil.which("claude")
    or "/Users/david.walker/.local/bin/claude"
)

_FOCUS_SCRIPT = """
tell application "iTerm2"
    set matchTab to "{tab}"
    set sessionId to "{session_id}"
    if matchTab is not "" then
        repeat with w in windows
            repeat with t in tabs of w
                repeat with s in sessions of t
                    if name of s contains matchTab then
                        select w
                        select t
                        return "focused"
                    end if
                end repeat
            end repeat
        end repeat
    end if
    tell current window
        create tab with default profile command "{claude_bin} --resume " & sessionId
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
        else:
            self._respond(404, {"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://localhost:7842")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

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
        else:
            self._respond(404, {"error": "not found"})

    def _handle_focus(self, body):
        session_id = body.get("session_id", "")
        tab = body.get("tab", "")
        if not session_id:
            self._respond(400, {"error": "session_id required"})
            return
        script = _FOCUS_SCRIPT.format(
            tab=tab.replace('"', '\\"'),
            session_id=session_id.replace('"', '\\"'),
            claude_bin=_CLAUDE_BIN.replace('"', '\\"'),
        )
        self._run_osascript(script)

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

    def _run_osascript(self, script):
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5
            )
            action = result.stdout.strip() or "ok"
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
