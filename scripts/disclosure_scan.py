#!/usr/bin/env python3
"""Disclosure scanner — blocks client info, personal paths, and stray secrets files.

Runs as a pre-commit hook (files are passed as arguments) and is also runnable by
hand: `python3 scripts/disclosure_scan.py $(git ls-files)`.

Complements gitleaks (which handles API keys/tokens). This script targets the
things a generic secret scanner misses:

  * client / project names that must never appear in a public repo — loaded from a
    denylist that is itself kept OUT of the repo (see below)
  * absolute home paths that leak a real username (/Users/<name>, /home/<name>)
  * internal email addresses
  * accidental staging of .env or *.db files

Denylist source (never committed — it would disclose the very names it protects):
  1. env var DISCLOSURE_DENYLIST — newline/comma separated (used by CI secrets)
  2. file .disclosure-denylist.txt at the repo root (gitignored)
One term per line; blank lines and lines starting with '#' are ignored.

Exit status: 0 = clean, 1 = findings (commit blocked), 2 = usage error.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

DENYLIST_FILE = ".disclosure-denylist.txt"

# Placeholder owners that are fine to ship in docs/comments/tests. Compared against
# the whole captured owner and its first dotted/dashed component, so "jane.doe" and
# "jane-doe" are both covered by "jane".
_PATH_ALLOW = {
    "jane", "john", "you", "user", "username", "me", "example",
    "ci", "runner", "home", "root", "someone", "yourname",
    "foo", "bar", "baz", "qux",
}


def _owner_allowed(owner: str) -> bool:
    o = owner.lower()
    return o in _PATH_ALLOW or re.split(r"[.\-]", o, maxsplit=1)[0] in _PATH_ALLOW
# Emails that are intentionally public / illustrative.
_EMAIL_ALLOW = re.compile(
    r"@(example\.(com|org|net)|anthropic\.com|users\.noreply\.github\.com)$",
    re.IGNORECASE,
)

_HOME_PATH = re.compile(r"/(?:Users|home)/([A-Za-z0-9._-]+)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Files that must never be committed even if not gitignored on someone's machine.
_FORBIDDEN_NAME = re.compile(r"(^|/)\.env(\.|$)|\.db$")
# .env.example is the one allowed .env* file.
_ALLOWED_ENV = re.compile(r"(^|/)\.env\.example$")

# Skip binary-ish and vendored paths outright.
_SKIP_DIRS = ("/.git/", "/.venv/", "/node_modules/", "/dist/", "/build/")
_BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz",
    ".db", ".sqlite", ".sqlite3", ".woff", ".woff2", ".ttf",
}


class Finding:
    def __init__(self, path: str, line: int, kind: str, detail: str):
        self.path = path
        self.line = line
        self.kind = kind
        self.detail = detail

    def __str__(self) -> str:
        loc = f"{self.path}:{self.line}" if self.line else self.path
        return f"  {loc}  [{self.kind}] {self.detail}"


def load_denylist(root: Path) -> list[str]:
    """Return lowercased client/project terms from env var or gitignored file."""
    raw = os.environ.get("DISCLOSURE_DENYLIST", "")
    terms: list[str] = []
    if raw:
        terms.extend(re.split(r"[\n,]", raw))
    else:
        f = root / DENYLIST_FILE
        if f.exists():
            terms.extend(f.read_text(encoding="utf-8").splitlines())
    out: list[str] = []
    for t in terms:
        t = t.strip()
        if t and not t.startswith("#"):
            out.append(t.lower())
    return out


def _is_scannable(path: str) -> bool:
    if any(seg in f"/{path}/" for seg in _SKIP_DIRS):
        return False
    return Path(path).suffix.lower() not in _BINARY_EXT


def scan_file(path: str, denylist: list[str]) -> list[Finding]:
    findings: list[Finding] = []

    # Forbidden filenames — flag regardless of content.
    if _FORBIDDEN_NAME.search(path) and not _ALLOWED_ENV.search(path):
        findings.append(Finding(path, 0, "forbidden-file",
                                "secrets/data file must not be committed"))
        return findings

    if not _is_scannable(path):
        return findings
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings  # unreadable or binary — nothing to scan

    for i, line in enumerate(text.splitlines(), start=1):
        low = line.lower()
        for term in denylist:
            if term in low:
                findings.append(Finding(path, i, "client-term", f"matched '{term}'"))
        for m in _HOME_PATH.finditer(line):
            if not _owner_allowed(m.group(1)):
                findings.append(Finding(path, i, "home-path", m.group(0)))
        for m in _EMAIL.finditer(line):
            if not _EMAIL_ALLOW.search(m.group(0)):
                findings.append(Finding(path, i, "email", m.group(0)))
    return findings


def main(argv: list[str]) -> int:
    files = argv[1:]
    if not files:
        print("disclosure_scan: no files given (nothing to check)", file=sys.stderr)
        return 0

    root = Path.cwd()
    denylist = load_denylist(root)
    if not denylist:
        print(
            f"disclosure_scan: no denylist found — client-name checks skipped.\n"
            f"  Create {DENYLIST_FILE} (gitignored) or set DISCLOSURE_DENYLIST to "
            f"enable them. See {DENYLIST_FILE.replace('.txt', '.example.txt')}.",
            file=sys.stderr,
        )

    all_findings: list[Finding] = []
    for path in files:
        if os.path.isfile(path):
            all_findings.extend(scan_file(path, denylist))

    if all_findings:
        print("Disclosure scan found potential leaks:\n", file=sys.stderr)
        for f in all_findings:
            print(str(f), file=sys.stderr)
        print(
            "\nIf a finding is a false positive, use a placeholder (e.g. /Users/you) "
            "or add an allowlist entry in scripts/disclosure_scan.py.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
