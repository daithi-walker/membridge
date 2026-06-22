"""Auto-summary of Claude sessions via Anthropic API or Vertex AI."""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

USE_VERTEX = os.getenv("CLAUDE_CODE_USE_VERTEX", "") == "1"
PROJECT_ID = os.getenv("ANTHROPIC_VERTEX_PROJECT_ID", "") or os.getenv("VERTEX_PROJECT_ID", "")
REGION = os.getenv("CLOUD_ML_REGION", "") or os.getenv("VERTEX_REGION", "global")
MODEL = os.getenv("CLAUDE_SUMMARY_MODEL", "claude-haiku-4-5-20251001")
MAX_TURNS = 20  # last N turns to include in summary prompt


def _get_client():
    if USE_VERTEX:
        from anthropic import AnthropicVertex
        return AnthropicVertex(project_id=PROJECT_ID, region=REGION)
    from anthropic import Anthropic
    return Anthropic()

SYSTEM_PROMPT = (
    "You are a concise technical assistant. "
    "Given a Claude Code session transcript, summarise in exactly 2 sentences: "
    "what the session was working on, and where it got to. "
    "Be specific — name the files, features, or bugs involved. "
    "Do not start with 'The session' or 'This session'."
)


def _read_transcript(transcript_path: str) -> list[dict] | None:
    path = Path(transcript_path)
    if not path.exists():
        return None
    turns = []
    try:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = obj.get("type") or obj.get("role")
                if role == "user":
                    content = obj.get("message", {})
                    if isinstance(content, dict):
                        text = " ".join(
                            b.get("text", "") for b in content.get("content", [])
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    else:
                        text = str(content)
                    if text.strip():
                        turns.append({"role": "user", "content": text.strip()})
                elif role == "assistant":
                    content = obj.get("message", {})
                    if isinstance(content, dict):
                        text = " ".join(
                            b.get("text", "") for b in content.get("content", [])
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    else:
                        text = str(content)
                    if text.strip():
                        turns.append({"role": "assistant", "content": text.strip()})
    except Exception as e:
        logger.warning("Failed to read transcript %s: %s", transcript_path, e)
        return None
    return turns[-MAX_TURNS:] if turns else None


def _format_turns(turns: list[dict]) -> str:
    lines = []
    for t in turns:
        prefix = "USER" if t["role"] == "user" else "CLAUDE"
        # Truncate very long turns
        content = t["content"][:500] + "…" if len(t["content"]) > 500 else t["content"]
        lines.append(f"{prefix}: {content}")
    return "\n\n".join(lines)


def summarise(transcript_path: str) -> str | None:
    turns = _read_transcript(transcript_path)
    if not turns:
        logger.info("No turns found in transcript %s", transcript_path)
        return None

    transcript_text = _format_turns(turns)
    prompt = f"Transcript:\n\n{transcript_text}\n\nSummarise this session in 2 sentences."

    try:
        client = _get_client()
        message = client.messages.create(
            model=MODEL,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        logger.warning("Summary generation failed: %s", e)
        return None
