"""Tests for scripts/disclosure_scan.py — the client-info / path / email guard."""
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "disclosure_scan.py"
_spec = importlib.util.spec_from_file_location("disclosure_scan", _SCRIPT)
ds = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(ds)


def _write(tmp_path, name: str, content: str) -> str:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return str(p)


# ── forbidden files ───────────────────────────────────────────────────────────

def test_env_file_is_forbidden(tmp_path):
    f = _write(tmp_path, ".env", "ANTHROPIC_API_KEY=sk-ant-real")
    findings = ds.scan_file(f, [])
    assert any(x.kind == "forbidden-file" for x in findings)


def test_env_example_is_allowed(tmp_path):
    f = _write(tmp_path, ".env.example", "ANTHROPIC_API_KEY=your-api-key\n")
    assert ds.scan_file(f, []) == []


def test_db_file_is_forbidden(tmp_path):
    f = _write(tmp_path, "sessions.db", "not really sqlite")
    findings = ds.scan_file(f, [])
    assert any(x.kind == "forbidden-file" for x in findings)


# ── home paths ────────────────────────────────────────────────────────────────

def test_real_home_path_flagged(tmp_path):
    # Build the literal at runtime so this test file itself stays scanner-clean.
    f = _write(tmp_path, "notes.md", "see /Users/" + "realperson/git/thing")
    findings = ds.scan_file(f, [])
    assert any(x.kind == "home-path" for x in findings)


def test_placeholder_home_path_allowed(tmp_path):
    f = _write(tmp_path, "notes.md", "example path /Users/you/git and /Users/jane/x")
    assert [x for x in ds.scan_file(f, []) if x.kind == "home-path"] == []


# ── emails ────────────────────────────────────────────────────────────────────

def test_internal_email_flagged(tmp_path):
    f = _write(tmp_path, "doc.md", "contact bob@" + "bigclient.com for access")
    findings = ds.scan_file(f, [])
    assert any(x.kind == "email" for x in findings)


def test_allowlisted_emails_pass(tmp_path):
    f = _write(tmp_path, "doc.md", "noreply@anthropic.com and dev@example.com")
    assert [x for x in ds.scan_file(f, []) if x.kind == "email"] == []


# ── client denylist ─────────────────────────────────────────────────────────---

def test_client_term_flagged_case_insensitive(tmp_path):
    f = _write(tmp_path, "readme.md", "We built this for AcmeCorp last quarter.")
    findings = ds.scan_file(f, ["acmecorp"])
    assert any(x.kind == "client-term" for x in findings)


def test_clean_file_passes(tmp_path):
    f = _write(tmp_path, "readme.md", "A generic local session tracker.\n")
    assert ds.scan_file(f, ["acmecorp"]) == []


# ── denylist loading ────────────────────────────────────────────────────────---

def test_load_denylist_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCLOSURE_DENYLIST", "Foo, Bar\n# comment\nBaz")
    assert ds.load_denylist(tmp_path) == ["foo", "bar", "baz"]


def test_load_denylist_from_file(monkeypatch, tmp_path):
    monkeypatch.delenv("DISCLOSURE_DENYLIST", raising=False)
    (tmp_path / ds.DENYLIST_FILE).write_text("# header\nAlpha\n\nBeta\n", encoding="utf-8")
    assert ds.load_denylist(tmp_path) == ["alpha", "beta"]


def test_load_denylist_env_takes_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCLOSURE_DENYLIST", "fromenv")
    (tmp_path / ds.DENYLIST_FILE).write_text("fromfile\n", encoding="utf-8")
    assert ds.load_denylist(tmp_path) == ["fromenv"]


# ── main() exit codes ─────────────────────────────────────────────────────────

def test_main_returns_1_on_finding(tmp_path):
    f = _write(tmp_path, ".env", "SECRET=x")
    assert ds.main(["prog", f]) == 1


def test_main_returns_0_when_clean(tmp_path):
    f = _write(tmp_path, "ok.md", "nothing to see here\n")
    assert ds.main(["prog", f]) == 0


def test_main_no_files_is_ok():
    assert ds.main(["prog"]) == 0
