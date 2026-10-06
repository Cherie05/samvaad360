FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-cloud.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-cloud.txt \
    && useradd --uid 10001 --create-home samvaad \
    && mkdir /data && chown samvaad /data
COPY --chown=samvaad:samvaad public_app /app/public_app
COPY --chown=samvaad:samvaad samvaad /app/samvaad
COPY --chown=samvaad:samvaad webhook /app/webhook
COPY --chown=samvaad:samvaad cloud /app/cloud
COPY --chown=samvaad:samvaad .streamlit/config.toml /app/.streamlit/config.toml
USER 10001
CMD ["uvicorn", "webhook.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
