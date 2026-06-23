"""iTerm2 focus and tab management via osascript — runs on the Mac host only."""
import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

_CLAUDE_BIN = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")

_FOCUS_BY_UUID = """
tell application "iTerm2"
    activate
    set targetUUID to "{uuid}"
    repeat with w in windows
        repeat with t in tabs of w
            repeat with s in sessions of t
                if unique ID of s is targetUUID then
                    select w
                    select t
                    return "focused"
                end if
            end repeat
        end repeat
    end repeat
    return "not_found"
end tell
"""

_FOCUS_BY_TTY = """
tell application "iTerm2"
    activate
    set targetTty to "{tty}"
    repeat with w in windows
        repeat with t in tabs of w
            repeat with s in sessions of t
                try
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

_OPEN_TAB = """
tell application "iTerm2"
    activate
    tell current window
        set newTab to (create tab with default profile)
        tell newTab
            repeat with s in sessions
                set name of s to "{tab_name}"
            end repeat
        end tell
        delay 0.8
        tell newTab
            repeat with s in sessions
                tell s to write text "cd {cwd} && {claude_bin} --resume {session_id}"
            end repeat
        end tell
    end tell
    return "opened"
end tell
"""

_RENAME = """
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

_LIST_SESSIONS = """
tell application "iTerm2"
    set output to {}
    repeat with w in windows
        repeat with t in tabs of w
            repeat with s in sessions of t
                set end of output to name of s
            end repeat
        end repeat
    end repeat
    return output
end tell
"""

_IS_FRONTMOST = """
tell application "iTerm2"
    if not frontmost then return "false"
    try
        set targetUUID to "{uuid}"
        set cs to current session of current tab of current window
        if unique ID of cs is targetUUID then return "true"
    end try
    return "false"
end tell
"""


def _run(script: str, timeout: int = 5) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout.strip()


def pid_to_tty(pid: int) -> str | None:
    try:
        result = subprocess.run(
            ["ps", "-o", "tty=", "-p", str(pid)],
            capture_output=True, text=True, timeout=3,
        )
        tty = result.stdout.strip()
        return tty if tty and tty != "??" else None
    except Exception:
        return None


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def focus_session(
    session_id: str,
    iterm_uuid: str | None = None,
    pid: int | None = None,
    cwd: str | None = None,
    tab_name: str | None = None,
) -> str:
    cwd = cwd or os.path.expanduser("~")
    tab_name = tab_name or session_id[:8]
    claude_bin = _CLAUDE_BIN or "claude"

    if iterm_uuid:
        script = _FOCUS_BY_UUID.format(uuid=iterm_uuid.replace('"', '\\"'))
        if _run(script) == "focused":
            return "focused"

    if pid:
        tty = pid_to_tty(pid)
        if tty:
            script = _FOCUS_BY_TTY.format(tty=tty.replace('"', '\\"'))
            if _run(script) == "focused":
                return "focused"

    script = _OPEN_TAB.format(
        cwd=cwd.replace('"', '\\"'),
        claude_bin=claude_bin.replace('"', '\\"'),
        session_id=session_id.replace('"', '\\"'),
        tab_name=tab_name.replace('"', '\\"'),
    )
    _run(script)
    return "opened"


def rename_tab(old_name: str, new_name: str) -> str:
    script = _RENAME.format(
        old_name=old_name.replace('"', '\\"'),
        new_name=new_name.replace('"', '\\"'),
    )
    return _run(script)


def list_sessions() -> list[str]:
    raw = _run(_LIST_SESSIONS)
    return [n.strip() for n in raw.split(",") if n.strip()]


def is_session_frontmost(iterm_uuid: str) -> bool:
    """Return True if iTerm2 is frontmost and this session's tab is active."""
    try:
        script = _IS_FRONTMOST.format(uuid=iterm_uuid.replace('"', '\\"'))
        return _run(script) == "true"
    except Exception:
        return False
