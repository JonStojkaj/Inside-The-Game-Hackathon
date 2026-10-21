# One container: FastAPI (REST + WebSocket replay) + the built web player + the exported matches.
# Build context is the REPO ROOT (needs frontend/ and data/export/):
#   docker build -f backend/Dockerfile .
# azd builds it remotely in Azure Container Registry (see infra/README.md), never on the dev Mac.

FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# api mode with VITE_API_BASE unset = same origin (/api/...)
ARG VITE_DATA_SOURCE=api
ARG VITE_MATCH_ID=full-34
ENV VITE_DATA_SOURCE=${VITE_DATA_SOURCE} VITE_MATCH_ID=${VITE_MATCH_ID}
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    EXPORT_DIR=/app/data/export \
    FRONTEND_DIR=/app/frontend/dist
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir . azure-monitor-opentelemetry
COPY data/export /app/data/export
COPY --from=frontend /src/frontend/dist /app/frontend/dist
RUN useradd --create-home --uid 1000 app
USER app
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
