# One container: FastAPI (REST + WebSocket replay) + the built web player + the baked exports.
# It only SERVES data/export/<match_id>/ (pre-computed insights/overlays): no LLM calls, no Azure OpenAI
# credentials, no recording, no simulation at runtime.
#
# Build context is the REPO ROOT (needs frontend/ and data/export/; see .dockerignore):
#   docker build --platform linux/amd64 -f backend/Dockerfile --build-arg VITE_MATCH_ID=demo-<n> .
# `azd up` builds it remotely in Azure Container Registry (azure.yaml, infra/README.md), never on the dev Mac.

# ---- stage 1: web player -------------------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# api mode with VITE_API_BASE unset = same origin (/api/...); the player opens VITE_MATCH_ID
# (any other baked match via ?match=<id>)
ARG VITE_DATA_SOURCE=api
ARG VITE_MATCH_ID
RUN test -n "${VITE_MATCH_ID}" || { echo "VITE_MATCH_ID is empty: azd env set DEMO_MATCH_ID demo-<n>" >&2; exit 1; }
ENV VITE_DATA_SOURCE=${VITE_DATA_SOURCE} VITE_MATCH_ID=${VITE_MATCH_ID}
RUN npm run build

# ---- stage 2: API runtime ------------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    EXPORT_DIR=/app/data/export \
    FRONTEND_DIR=/app/frontend/dist
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
# azure-monitor-opentelemetry: tracing to Application Insights when APPLICATIONINSIGHTS_CONNECTION_STRING is set
RUN pip install --no-cache-dir . "azure-monitor-opentelemetry>=1.6" && rm -rf build ./*.egg-info

COPY data/export /app/data/export
COPY --from=frontend /src/frontend/dist /app/frontend/dist
# fail the build (not the demo) if the selected match was not exported
ARG VITE_MATCH_ID
RUN test -f "/app/data/export/${VITE_MATCH_ID}/match.json" \
    || { echo "data/export/${VITE_MATCH_ID}/match.json missing: run spikes/export_demo.py first" >&2; exit 1; }

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001:10001
EXPOSE 8000
# Container Apps uses its own probes (infra/resources.bicep); this one is for plain `docker run`
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=4)" || exit 1
CMD ["sh", "-c", "exec uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
