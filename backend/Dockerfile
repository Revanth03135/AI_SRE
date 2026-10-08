# Build from the backend/ directory (see render.yaml: dockerContext).
# The image serves the incident API only; the agent pipeline needs ML dependencies, Qdrant and a
# kubeconfig, which this slim image does not include.
FROM python:3.12-slim

WORKDIR /app

COPY requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

COPY ai_sre/__init__.py ./ai_sre/__init__.py
COPY ai_sre/api ./ai_sre/api
COPY ai_sre/executor ./ai_sre/executor
COPY ai_sre/mcp_servers ./ai_sre/mcp_servers

EXPOSE 8000

CMD ["sh", "-c", "uvicorn ai_sre.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
