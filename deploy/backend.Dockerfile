FROM python:3.13.7-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH
WORKDIR /app

RUN pip install --no-cache-dir uv==0.8.13
COPY pyproject.toml uv.lock README.md ./
COPY backend ./backend
RUN uv sync --frozen --no-dev --extra worker

COPY alembic.ini ./
COPY migrations ./migrations
COPY worker ./worker
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 taskmarshal && chown -R taskmarshal:taskmarshal /app
USER taskmarshal

CMD ["uvicorn", "taskmarshal.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
