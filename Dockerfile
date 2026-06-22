FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY claude_ui/ claude_ui/
RUN uv pip install --system --no-cache .

EXPOSE 7842

CMD ["uvicorn", "claude_ui.server:app", "--host", "0.0.0.0", "--port", "7842"]
