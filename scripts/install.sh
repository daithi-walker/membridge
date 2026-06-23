#!/bin/bash
# MemBridge install script
# - Builds the Docker image
# - Registers Claude Code hooks in ~/.claude/settings.json
# - Installs a launchd plist for the focus server (port 7843)
#
# Prerequisites:
#   - Docker / OrbStack installed and running
#   - Python 3.11+ on PATH
#   - .env file with VERTEX_PROJECT_ID set (copy .env.example)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_DIR="$PROJECT_DIR/hooks"
SETTINGS_FILE="$HOME/.claude/settings.json"
PLIST_LABEL="com.daihi.membridge"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
DOCKER_BIN="$(command -v docker)"

echo "==> MemBridge installer"
echo "    Project: $PROJECT_DIR"

# ── 1. Build Docker image ─────────────────────────────────────────────────────
echo ""
echo "==> Building Docker image..."
"$DOCKER_BIN" compose -f "$PROJECT_DIR/docker-compose.yml" build
echo "    Image built: membridge:latest"

# ── 2. Create data directory ──────────────────────────────────────────────────
mkdir -p "$HOME/.membridge"
echo "    Data dir: $HOME/.membridge"

# ── 2b. Install Claude Code slash commands ────────────────────────────────────
echo ""
echo "==> Installing Claude Code commands..."
mkdir -p "$HOME/.claude/commands"
cp "$PROJECT_DIR/commands/summarize.md" "$HOME/.claude/commands/summarize.md"
echo "    /summarize → ~/.claude/commands/summarize.md"

# ── 3. Register hooks in ~/.claude/settings.json ──────────────────────────────
echo ""
echo "==> Registering hooks in $SETTINGS_FILE..."

HEARTBEAT_HOOK="$HOOKS_DIR/claude_ui_heartbeat.sh"
TOOL_USE_HOOK="$HOOKS_DIR/claude_ui_tool_use.sh"
STOP_HOOK="$HOOKS_DIR/claude_ui_stop.sh"

[ -f "$SETTINGS_FILE" ] || echo '{}' > "$SETTINGS_FILE"

python3 - "$SETTINGS_FILE" "$HEARTBEAT_HOOK" "$TOOL_USE_HOOK" "$STOP_HOOK" << 'PYEOF'
import json, sys

settings_path, heartbeat_hook, tool_use_hook, stop_hook = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

with open(settings_path) as f:
    settings = json.load(f)

hooks = settings.setdefault("hooks", {})

def register(event, command):
    event_hooks = hooks.setdefault(event, [])
    already = any(
        any(h.get("command") == command for h in e.get("hooks", []))
        for e in event_hooks
    )
    if not already:
        event_hooks.append({"hooks": [{"type": "command", "command": command}]})
        print(f"  Added {event} hook: {command}")
    else:
        print(f"  {event} hook already registered")

register("UserPromptSubmit", heartbeat_hook)
register("PreToolUse", tool_use_hook)
register("Stop", stop_hook)

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PYEOF

PYTHON_BIN="$(command -v python3)"

# ── 4. Install launchd plists ─────────────────────────────────────────────────
echo ""
echo "==> Installing launchd services..."

mkdir -p "$HOME/Library/LaunchAgents"

# 4a. Main app (Docker)
cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${PLIST_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${DOCKER_BIN}</string>
    <string>compose</string>
    <string>-f</string>
    <string>${PROJECT_DIR}/docker-compose.yml</string>
    <string>up</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/membridge.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/membridge.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>${HOME}</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "    Loaded: $PLIST_LABEL (port 7842)"

# 4b. Focus server (host Python — needs osascript access to iTerm2)
FOCUS_PLIST_LABEL="com.daihi.membridge-focus"
FOCUS_PLIST_PATH="$HOME/Library/LaunchAgents/${FOCUS_PLIST_LABEL}.plist"

# Detect iTerm2 bundled Python for sync-tabs (titleOverride API)
ITERM2_PYTHON_BIN=""
for candidate in "$HOME/Library/Application Support/iTerm2"/iterm2env-*/versions/3.14.0/bin/python3.14; do
  if [ -x "$candidate" ] && "$candidate" -c "import iterm2" 2>/dev/null; then
    ITERM2_PYTHON_BIN="$candidate"
    break
  fi
done

if [ -n "$ITERM2_PYTHON_BIN" ]; then
  echo "    iTerm2 Python: $ITERM2_PYTHON_BIN"
  ITERM2_ENV_BLOCK="  <key>EnvironmentVariables</key>
  <dict>
    <key>ITERM2_PYTHON</key>
    <string>${ITERM2_PYTHON_BIN}</string>
  </dict>"
else
  echo "    iTerm2 Python runtime not found — tab alias sync will use osascript fallback"
  ITERM2_ENV_BLOCK=""
fi

cat > "$FOCUS_PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${FOCUS_PLIST_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>${PROJECT_DIR}/scripts/focus_server.py</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/membridge-focus.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/membridge-focus.log</string>
${ITERM2_ENV_BLOCK}
</dict>
</plist>
PLIST

launchctl unload "$FOCUS_PLIST_PATH" 2>/dev/null || true
launchctl load "$FOCUS_PLIST_PATH"
echo "    Loaded: $FOCUS_PLIST_LABEL (port 7843)"

# ── 5. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "==> All done!"
echo ""
echo "    Dashboard:   http://localhost:7842"
echo "    App logs:    tail -f /tmp/membridge.log"
echo "    Focus logs:  tail -f /tmp/membridge-focus.log"
echo "    DB:          ~/.membridge/sessions.db"
echo "    Commands:    /summarize (in any Claude Code session)"
echo ""
echo "    Hooks registered — restart Claude Code to pick them up."
