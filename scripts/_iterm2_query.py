#!/usr/bin/env python3
"""
Query iTerm2 tab state via the Python API (requires iTerm2 shell integration
and the iTerm2 Python runtime to be installed).

Prints JSON: list of {uuid, tty, name, title_override}
  - uuid:           session UUID (matches $ITERM_SESSION_ID after the colon)
  - tty:            /dev/ttysXXX
  - name:           auto-generated name (spinner + AI summary)
  - title_override: user-set tab alias, or null if not set

Usage (called as a subprocess by sync_iterm_tabs.py):
    /path/to/iterm2env python3 _iterm2_query.py
"""

import json

import iterm2


async def main(connection):
    app = await iterm2.async_get_app(connection)
    results = []
    for window in app.terminal_windows:
        for tab in window.tabs:
            title_override = await tab.async_get_variable("titleOverride")
            for session in tab.sessions:
                tty = await session.async_get_variable("tty")
                results.append({
                    "uuid":           session.session_id,
                    "tty":            tty,
                    "name":           session.name,
                    "title_override": title_override or None,
                })
    print(json.dumps(results))


iterm2.run_until_complete(main)
