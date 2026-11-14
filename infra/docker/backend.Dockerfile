# Backend image (plan F-06: Python 3.11, FastAPI, ONNX Runtime CPU). Build context = repository root.
# Models are mounted at /app/models in development (docker-compose.yml) and baked in at T6.1 (production image).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install exactly the pinned runtime dependencies from backend/pyproject.toml (no dev extras).
COPY backend/pyproject.toml /tmp/pyproject.toml
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('/tmp/pyproject.toml','rb'))['project']['dependencies']))" > /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt

# Keep the repo layout so app.config resolves BACKEND_DIR=/app/backend and REPO_ROOT=/app.
COPY backend/app /app/backend/app
COPY backend/config /app/backend/config
ENV PYTHONPATH=/app/backend

RUN useradd --create-home --uid 10001 kiosk \
 && mkdir -p /app/data /app/models \
 && chown -R kiosk:kiosk /app/data /app/models
USER kiosk

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
