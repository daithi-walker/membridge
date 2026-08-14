"""iTerm2 focus and tab management via osascript — runs on the Mac host only."""
import glob
import logging
import os
import re
import shutil
import subprocess

from . import sesh as _sesh

logger = logging.getLogger(__name__)

_CLAUDE_BIN = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")

_PROJECTS_DIR = os.path.expanduser("~/.claude/projects")


def resume_cwd(session_id: str, fallback: str | None) -> str | None:
    """Return the directory `claude --resume <session_id>` must be launched from.

    Claude Code stores a session's transcript at
    ~/.claude/projects/<encoded-cwd>/<session_id>.jsonl, and `--resume` only finds
    it when the *current* cwd maps to that same folder. So the correct target is
    whatever real directory the transcript's folder encodes — NOT the DB cwd, which
    a heartbeat may have captured mid-session as the cwd moved (worktrees, cd).

    The folder encoding is lossy (both '/' and '.' collapse to '-'), so we can't
    reverse it by string substitution; we walk the filesystem to find the real path
    that re-encodes to the folder name. Falls back to `fallback` (the DB cwd) when
    the transcript is gone or the folder can't be resolved on disk — i.e. exactly
    the previous behavior.
    """
    paths = glob.glob(os.path.join(_PROJECTS_DIR, "*", f"{session_id}.jsonl"))
    if not paths:
        return fallback
    path = max(paths, key=os.path.getmtime)
    folder = os.path.basename(os.path.dirname(path))
    decoded = _decode_project_folder(folder)
    return decoded if decoded else fallback


def _decode_project_folder(folder: str) -> str | None:
    """Reverse a ~/.claude/projects folder name to a real absolute directory.

    The name is the launch cwd with every '/' and '.' replaced by '-', which is
    lossy. We resolve the ambiguity by walking the filesystem: at each path
    component we accept any existing child directory whose name re-encodes to a
    prefix of what's left. Returns the first fully-resolved existing path, or None.
    """
    if not folder.startswith("-"):
        return None
    stack = [("/", folder[1:])]  # leading '-' is the root '/'
    while stack:
        base, rem = stack.pop()
        if rem == "":
            return base
        try:
            children = os.listdir(base)
        except OSError:
            continue
        # Longest names first so multi-token components (e.g. "cro-data-contracts")
        # win over shorter prefixes, keeping the walk deterministic.
        for child in sorted(children, key=len, reverse=True):
            nxt = os.path.join(base, child)
            if not os.path.isdir(nxt):
                continue
            enc = child.replace(".", "-")
            if rem == enc:
                stack.append((nxt, ""))
            elif rem.startswith(enc + "-"):
                stack.append((nxt, rem[len(enc) + 1:]))
    return None

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
                tell s to write text "cd {cwd} && {resume_cmd}"
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


_SAFE_PATH_RE = re.compile(r'^[\w/\-. ]+$')
_SAFE_ID_RE   = re.compile(r'^[a-zA-Z0-9_\-]+$')


def _safe_path(value: str) -> str:
    """Raise if value contains characters that could escape an AppleScript shell write."""
    if not _SAFE_PATH_RE.match(value):
        raise ValueError(f"Unsafe path for AppleScript: {value!r}")
    return value


def _safe_id(value: str) -> str:
    """Raise if session_id contains characters that could escape an AppleScript shell write."""
    if not _SAFE_ID_RE.match(value):
        raise ValueError(f"Unsafe session_id for AppleScript: {value!r}")
    return value


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

    # Reached only when live focus (UUID/TTY) failed — we're opening a fresh tab
    # to `--resume`. Resolve the cwd the transcript actually lives under, since the
    # DB cwd can be stale for worktree / multi-cd sessions (see resume_cwd).
    cwd = resume_cwd(session_id, cwd) or cwd

    try:
        safe_cwd = _safe_path(cwd)
        safe_sid = _safe_id(session_id)
    except ValueError as e:
        logger.warning("focus_session: %s — falling back to home dir open", e)
        safe_cwd = os.path.expanduser("~")
        safe_sid = session_id[:8] if _SAFE_ID_RE.match(session_id[:8]) else "claude"

    resume_cmd = _resume_command(claude_bin, safe_cwd, safe_sid)
    script = _OPEN_TAB.format(
        cwd=safe_cwd.replace('"', '\\"'),
        resume_cmd=resume_cmd.replace('"', '\\"'),
        tab_name=tab_name.replace('"', '\\"'),
    )
    _run(script)
    return "opened"


def _resume_command(claude_bin: str, cwd: str, session_id: str) -> str:
    """Shell command to resume a session, preferring sesh where the project opted in.

    When the project has a `.sesh/` archive, try `sesh resume <id>` first: it
    resumes the live session directly if present, else materializes it from a
    snapshot. It exits non-zero when it knows nothing of the id, so we fall back
    to plain `claude --resume`. Both are already shell-safe (see _safe_* guards).
    """
    claude_resume = f"{claude_bin} --resume {session_id}"
    try:
        if _sesh.available() and _sesh.is_enabled(cwd):
            sesh_bin = _sesh._SESH_BIN
            if sesh_bin and _SAFE_PATH_RE.match(sesh_bin):
                return f"{sesh_bin} resume {session_id} || {claude_resume}"
    except Exception as e:
        logger.debug("sesh resume preference skipped: %s", e)
    return claude_resume


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
