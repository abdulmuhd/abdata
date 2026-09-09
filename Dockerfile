FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/zaply

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY frontend ./frontend
COPY scripts/entrypoint.sh ./scripts/entrypoint.sh
RUN chmod +x scripts/entrypoint.sh

# Non-root runtime user
RUN useradd -r -u 10001 zaply && chown -R zaply /srv/zaply
USER zaply

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')" || exit 1

ENTRYPOINT ["./scripts/entrypoint.sh"]
