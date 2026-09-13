"""Settings read from environment variables.

Local (Docker):  DDB_ENDPOINT=http://localhost:8000 + dummy AWS keys
EC2 (prod):      DDB_ENDPOINT unset -> boto3 uses the instance role automatically
"""
import os

TABLE_NAME: str = os.getenv("TABLE_NAME", "incident_memory")
AWS_REGION: str = os.getenv("AWS_REGION", "eu-central-1")
DDB_ENDPOINT: str | None = os.getenv("DDB_ENDPOINT") or None
MCP_TRANSPORT: str = os.getenv("MCP_TRANSPORT", "stdio")  # "stdio" | "streamable-http"
HTTP_HOST: str = os.getenv("HTTP_HOST", "0.0.0.0")
HTTP_PORT: int = int(os.getenv("HTTP_PORT", "8080"))
