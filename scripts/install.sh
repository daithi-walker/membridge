#!/bin/bash
# MemBridge install script — native host process, no Docker.
#
# What this does:
#   - Creates a uv venv and installs the package
#   - Registers Claude Code hooks in ~/.claude/settings.json
#   - Installs a single launchd plist (com.daihi.membridge) on port 7842
#   - Stops the Docker container and removes the old focus-server plist if present
#
# Prerequisites:
#   - uv installed (https://docs.astral.sh/uv/)
#   - .env file with ANTHROPIC_API_KEY set (copy .env.example)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_DIR="$PROJECT_DIR/hooks"
SETTINGS_FILE="$HOME/.claude/settings.json"

PLIST_LABEL="com.daihi.membridge"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
OLD_FOCUS_PLIST="$HOME/Library/LaunchAgents/com.daihi.membridge-focus.plist"

echo "==> MemBridge installer (native)"
echo "    Project: $PROJECT_DIR"

# ── 1. Stop old services ──────────────────────────────────────────────────────
echo ""
echo "==> Stopping old services..."
# Stop Docker container if running
if command -v docker &>/dev/null; then
  docker compose -f "$PROJECT_DIR/docker-compose.yml" down 2>/dev/null || true
fi
# Remove old focus server plist
if [ -f "$OLD_FOCUS_PLIST" ]; then
  launchctl unload "$OLD_FOCUS_PLIST" 2>/dev/null || true
  rm -f "$OLD_FOCUS_PLIST"
  echo "    Removed old focus plist"
fi

# ── 2. Create venv + install ──────────────────────────────────────────────────
echo ""
echo "==> Installing Python package..."
cd "$PROJECT_DIR"
uv venv --python 3.12 --clear .venv
uv pip install --python .venv/bin/python --no-cache -e .
echo "    Installed: $PROJECT_DIR/.venv"

# ── 3. Data directory ─────────────────────────────────────────────────────────
mkdir -p "$HOME/.membridge"
echo "    Data dir: $HOME/.membridge"

# ── 4. Claude Code slash commands ─────────────────────────────────────────────
echo ""
echo "==> Installing Claude Code commands..."
mkdir -p "$HOME/.claude/commands"
for cmd in membridge-summarize membridge-archive membridge-context; do
  if [ -f "$PROJECT_DIR/commands/$cmd.md" ]; then
    cp "$PROJECT_DIR/commands/$cmd.md" "$HOME/.claude/commands/$cmd.md"
    echo "    /$cmd → ~/.claude/commands/$cmd.md"
  fi
done
rm -f "$HOME/.claude/commands/summarize.md"
rm -f "$HOME/.claude/commands/membridge-recall.md"

# ── 5. Register hooks ─────────────────────────────────────────────────────────
echo ""
echo "==> Registering hooks in $SETTINGS_FILE..."

HEARTBEAT_HOOK="$HOOKS_DIR/claude_ui_heartbeat.sh"
TOOL_USE_HOOK="$HOOKS_DIR/claude_ui_tool_use.sh"
STOP_HOOK="$HOOKS_DIR/claude_ui_stop.sh"
NOTIFICATION_HOOK="$HOOKS_DIR/claude_ui_notification.sh"

[ -f "$SETTINGS_FILE" ] || echo '{}' > "$SETTINGS_FILE"

python3 - "$SETTINGS_FILE" "$HEARTBEAT_HOOK" "$TOOL_USE_HOOK" "$STOP_HOOK" "$NOTIFICATION_HOOK" << 'PYEOF'
import json, sys
settings_path, heartbeat_hook, tool_use_hook, stop_hook, notification_hook = sys.argv[1:]
with open(settings_path) as f:
    settings = json.load(f)
hooks = settings.setdefault("hooks", {})
def register(event, command, matcher=None):
    event_hooks = hooks.setdefault(event, [])
    already = any(
        any(h.get("command") == command for h in e.get("hooks", []))
        for e in event_hooks
    )
    if not already:
        entry = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            entry["matcher"] = matcher
        event_hooks.append(entry)
        print(f"  Added {event} hook: {command}")
    else:
        print(f"  {event} hook already registered")
register("UserPromptSubmit", heartbeat_hook)
register("PreToolUse", tool_use_hook)
register("Stop", stop_hook)
register("Notification", notification_hook, matcher="permission_prompt")
with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PYEOF

# ── 6. launchd plist ──────────────────────────────────────────────────────────
echo ""
echo "==> Installing launchd service..."
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${PLIST_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PROJECT_DIR}/scripts/run.sh</string>
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
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "    Loaded: $PLIST_LABEL (port 7842)"

# ── 7. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "==> All done!"
echo ""
echo "    Dashboard:  http://localhost:7842"
echo "    Logs:       tail -f /tmp/membridge.log"
echo "    DB:         ~/.membridge/sessions.db"
echo ""
echo "    Hooks registered — restart Claude Code to pick them up."
