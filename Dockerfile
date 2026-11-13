FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CODER_BUDDY_DATA_DIR=/app/data
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev
COPY agent ./agent
COPY web ./web
COPY app.py main.py ./
RUN useradd --uid 10001 --create-home appuser && mkdir /app/data && chown appuser:appuser /app/data
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]
CMD ["/app/.venv/bin/uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
