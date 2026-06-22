#!/bin/bash
# claude-ui install script
# - Builds the Docker image
# - Registers Claude Code hooks in ~/.claude/settings.json
# - Installs a launchd plist to start the container at login

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_DIR="$PROJECT_DIR/hooks"
SETTINGS_FILE="$HOME/.claude/settings.json"
PLIST_LABEL="com.daihi.claude-ui"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
DOCKER_BIN="$(command -v docker)"

echo "==> claude-ui installer"
echo "    Project: $PROJECT_DIR"

# ── 1. Build Docker image ─────────────────────────────────────────────────────
echo ""
echo "==> Building Docker image..."
"$DOCKER_BIN" compose -f "$PROJECT_DIR/docker-compose.yml" build
echo "    Image built: claude-ui:latest"

# ── 2. Create data directory ──────────────────────────────────────────────────
mkdir -p "$HOME/.claude-ui"
echo "    Data dir: $HOME/.claude-ui"

# ── 3. Register hooks in ~/.claude/settings.json ──────────────────────────────
echo ""
echo "==> Registering hooks in $SETTINGS_FILE..."

HEARTBEAT_HOOK="$HOOKS_DIR/claude_ui_heartbeat.sh"
STOP_HOOK="$HOOKS_DIR/claude_ui_stop.sh"

[ -f "$SETTINGS_FILE" ] || echo '{}' > "$SETTINGS_FILE"

python3 - "$SETTINGS_FILE" "$HEARTBEAT_HOOK" "$STOP_HOOK" << 'PYEOF'
import json, sys

settings_path, heartbeat_hook, stop_hook = sys.argv[1], sys.argv[2], sys.argv[3]

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
register("Stop", stop_hook)

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PYEOF

# ── 4. Install launchd plist ─────────────────────────────────────────────────
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
  <string>/tmp/claude-ui.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/claude-ui.log</string>
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
echo "    Service loaded: $PLIST_LABEL"

# ── 5. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "==> All done!"
echo ""
echo "    Dashboard:  http://localhost:7842"
echo "    Logs:       tail -f /tmp/claude-ui.log"
echo "    DB:         ~/.claude-ui/sessions.db"
echo "    Container:  docker compose -f $PROJECT_DIR/docker-compose.yml ps"
echo ""
echo "    Hooks registered — restart Claude Code to pick them up."
