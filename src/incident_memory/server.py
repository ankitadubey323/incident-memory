"""MCP server — exposes the incident store as tools, a resource and a prompt.

Run locally (stdio):      uv run incident-memory
Run as HTTP service:      MCP_TRANSPORT=streamable-http uv run incident-memory
"""
from typing import Literal

from mcp.server.mcpserver import MCPServer  # mcp 2.x (was FastMCP in 1.x)

from . import config, db

mcp = MCPServer(
    "incident-memory",
    instructions="Long-term memory of production incidents. Search history before "
                 "diagnosing an alert; record incidents and their fixes for the future.",
)

Severity = Literal["sev1", "sev2", "sev3", "sev4"]


# ------------------------------------------------------------------ tools
@mcp.tool()
def record_incident(service: str, severity: Severity, summary: str,
                    root_cause: str = "", fix: str = "") -> dict:
    """Record a new production incident for a service. Use this when a user reports
    an outage, alert or degradation. Returns the created incident including its
    incident_id, which is needed to resolve it later."""
    return db.record_incident(service, severity, summary, root_cause, fix)


@mcp.tool()
def find_similar_incidents(service: str, keyword: str | None = None, limit: int = 5) -> list[dict]:
    """Search past incidents of a service, newest first. Optionally filter by a keyword
    that appears in the summary or root cause (e.g. '503', 'redis', 'timeout').
    Use this first when a user asks whether a problem has happened before."""
    return db.find_similar(service, keyword, limit)


@mcp.tool()
def get_incident(incident_id: str) -> dict | None:
    """Fetch a single incident by its incident_id."""
    return db.get_incident(incident_id)


@mcp.tool()
def update_incident_status(incident_id: str, root_cause: str, fix: str) -> dict:
    """Mark an open incident as resolved, recording the confirmed root cause and fix.
    Fails if the incident is already resolved."""
    return db.resolve_incident(incident_id, root_cause, fix)


@mcp.tool()
def list_open_incidents(limit: int = 20) -> list[dict]:
    """List currently open incidents across all services, newest first."""
    return db.list_open(limit)


@mcp.tool()
def add_runbook_note(service: str, note: str, author: str = "claude", ttl_days: int = 30) -> dict:
    """Attach a temporary runbook note to a service (e.g. a workaround or a contact).
    The note expires automatically after ttl_days."""
    return db.add_note(service, note, author, ttl_days)


@mcp.tool()
def service_stats(service: str) -> dict:
    """Return incident_count and last_incident_at for a service."""
    return db.service_stats(service)


# ------------------------------------------------------------------ resource
@mcp.resource("incident://{service}/latest")
def latest_incident(service: str) -> str:
    """The most recent incident recorded for a service."""
    items = db.find_similar(service, limit=1)
    return str(items[0]) if items else f"No incidents recorded for {service}."


# ------------------------------------------------------------------ prompt
@mcp.prompt()
def triage_alert(service: str, alert_text: str) -> str:
    """Guide the model through triaging a new alert using past incident history."""
    return (
        f"An alert fired for service '{service}': {alert_text}\n\n"
        "1. Call find_similar_incidents to check whether this has happened before.\n"
        "2. Summarise the most likely root cause and the fixes that worked previously.\n"
        "3. Ask the user whether to record a new incident with record_incident."
    )


def main() -> None:
    if config.MCP_TRANSPORT == "streamable-http":
        # HTTP mode (EC2): nginx proxies to this port; bind to all interfaces inside Docker.
        mcp.run(transport="streamable-http", host=config.HTTP_HOST, port=config.HTTP_PORT)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
