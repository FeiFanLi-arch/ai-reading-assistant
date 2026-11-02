FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_PATH=/app/data/reader.db
WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && groupadd --gid 10001 reader \
    && useradd --uid 10001 --gid reader --no-create-home reader \
    && mkdir -p /app/data \
    && chown reader:reader /app/data

COPY --chown=reader:reader backend ./backend
COPY --chown=reader:reader frontend ./frontend
USER reader
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
