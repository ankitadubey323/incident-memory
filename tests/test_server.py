"""Tests for the MCP layer — talks to the server in-process through a real MCP client."""
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
import pytest
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams


@asynccontextmanager
async def connect() -> AsyncIterator[ClientSession]:
    """In-process MCP client connected to the server over memory streams (no subprocess)."""
    from incident_memory import server

    lowlevel = server.mcp._lowlevel_server
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as tg:
            tg.start_soon(
                lowlevel.run, *server_streams, lowlevel.create_initialization_options(),
            )
            async with ClientSession(*client_streams) as s:
                await s.initialize()
                yield s
            tg.cancel_scope.cancel()


@pytest.fixture
def session(db):
    """Usable as `async with session as s:` — `db` guarantees the mocked table exists."""
    return connect()


async def test_lists_all_primitives(session):
    async with session as s:
        tools = {t.name for t in (await s.list_tools()).tools}
        assert tools == {
            "record_incident", "find_similar_incidents", "get_incident",
            "update_incident_status", "list_open_incidents", "add_runbook_note", "service_stats",
        }
        templates = [str(t.uri_template) for t in (await s.list_resource_templates()).resource_templates]
        assert templates == ["incident://{service}/latest"]
        assert [p.name for p in (await s.list_prompts()).prompts] == ["triage_alert"]


async def test_record_then_find_then_resolve(session):
    async with session as s:
        r = await s.call_tool(
            "record_incident",
            {"service": "checkout", "severity": "sev2", "summary": "503 on /pay"},
        )
        inc = json.loads(r.content[0].text)
        assert inc["status"] == "open"

        r = await s.call_tool("find_similar_incidents", {"service": "checkout", "keyword": "503"})
        assert "503 on /pay" in r.content[0].text

        r = await s.call_tool(
            "update_incident_status",
            {"incident_id": inc["incident_id"], "root_cause": "redis", "fix": "restart"},
        )
        assert json.loads(r.content[0].text)["status"] == "resolved"

        # second resolve is rejected by the DynamoDB condition expression
        r = await s.call_tool(
            "update_incident_status",
            {"incident_id": inc["incident_id"], "root_cause": "x", "fix": "y"},
        )
        assert r.is_error


async def test_invalid_severity_is_rejected_by_schema(session):
    async with session as s:
        r = await s.call_tool(
            "record_incident", {"service": "checkout", "severity": "sev9", "summary": "x"}
        )
        assert r.is_error


async def test_resource_and_prompt(session):
    async with session as s:
        r = await s.read_resource("incident://checkout/latest")
        assert "No incidents" in r.contents[0].text

        p = await s.get_prompt("triage_alert", {"service": "checkout", "alert_text": "503s"})
        assert "find_similar_incidents" in p.messages[0].content.text
