# Production image for the MCP server (Streamable HTTP on :8080).
#   docker build -t incident-memory -f deploy/Dockerfile .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=streamable-http \
    HTTP_HOST=0.0.0.0 \
    HTTP_PORT=8080 \
    TABLE_NAME=incident_memory \
    AWS_REGION=eu-central-1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
 && useradd --system --no-create-home app
USER app

EXPOSE 8080
CMD ["incident-memory"]
