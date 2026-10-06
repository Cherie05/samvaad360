FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SAMVAAD_DB_PATH=/var/lib/samvaad/pilot.db
WORKDIR /app
COPY infra/voice/requirements.txt /app/voice-requirements.txt
RUN pip install --no-cache-dir -r /app/voice-requirements.txt
COPY samvaad /app/samvaad
COPY webhook /app/webhook
COPY cloud /app/cloud
COPY public_app /app/public_app
COPY tools /app/tools
RUN useradd --uid 10001 --create-home samvaad && mkdir -p /var/lib/samvaad && chown samvaad /var/lib/samvaad
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["python", "-m", "uvicorn", "webhook.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
