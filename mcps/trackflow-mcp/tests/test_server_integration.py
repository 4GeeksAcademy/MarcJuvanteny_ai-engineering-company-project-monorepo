"""Round-trip real, de punta a punta: un servidor MCP real (Starlette +
FastMCP + MCP Auth, exactamente `server.build_app()`) corriendo en un
thread de uvicorn sobre 127.0.0.1, consultado con `fastmcp.Client` (el
cliente MCP real), igual que lo haria un agente externo -- initialize,
tools/list, tools/call, con y sin bearer token.

Las llamadas de las tools al backend de `incidents-api` se parchean via
`httpx.MockTransport` (monkeypatch de `httpx.Client`, mismo proceso) para no
depender de un servicio corriendo -- pero el protocolo MCP, el transporte
HTTP real (sockets de verdad en localhost) y el middleware de OAuth de
`mcpauth` son reales, sin dobles.
"""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastmcp import Client
from fastmcp.exceptions import ToolError

import server
from dev_idp import DevIdP


class _ThreadServer(uvicorn.Server):
    def install_signal_handlers(self) -> None:
        pass


@pytest.fixture()
def running_server(test_mcp_auth, test_verify_fn, monkeypatch):
    _CATALOG = [
        {
            "id": 1,
            "name": "Auriculares inalambricos Pro",
            "sku": "TEC-EAR-001",
            "client_name": "SoundWave Electronics",
            "category": "electronics",
            "warehouse": "LA",
            "current_stock": 3,
        }
    ]
    _INCIDENT = {
        "id": 7,
        "title": "Paquete perdido",
        "description": "El paquete nunca llego",
        "category": "lost_parcel",
        "origin": "customer",
        "branch": "la_warehouse",
        "status": "open",
        "source_incident_id": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    def fake_backend_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/incidents/7":
            return httpx.Response(200, json=_INCIDENT)
        if request.url.path == "/inventory/products":
            return httpx.Response(200, json=_CATALOG)
        return httpx.Response(404, json={"detail": "not found"})

    real_client_cls = httpx.Client

    def fake_client_factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client_cls(*args, transport=httpx.MockTransport(fake_backend_handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", fake_client_factory)

    app = server.build_app(mcp_auth=test_mcp_auth, verify_mode=test_verify_fn)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    config = uvicorn.Config(app=app, log_level="warning")
    thread_server = _ThreadServer(config)
    thread = threading.Thread(target=thread_server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()

    deadline = time.monotonic() + 5
    while not thread_server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert thread_server.started, "el servidor de prueba no arranco a tiempo"

    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        thread_server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.anyio
async def test_unauthenticated_client_cannot_list_tools(running_server):
    client = Client(running_server)

    with pytest.raises(Exception):
        async with client:
            await client.list_tools()


@pytest.mark.anyio
async def test_authenticated_client_with_scope_can_query_incident(running_server, dev_idp: DevIdP):
    token = dev_idp.issue_token(scopes=["mcp:access", "incidents:read"])
    client = Client(running_server, auth=token)

    async with client:
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools}
        assert "query_incident_tool" in tool_names

        result = await client.call_tool("query_incident_tool", {"query": {"incident_id": 7}})
        payload = result.structured_content
        assert payload["ok"] is True
        assert payload["incidents"][0]["status"] == "open"


@pytest.mark.anyio
async def test_authenticated_client_without_required_scope_is_rejected_by_the_tool(running_server, dev_idp: DevIdP):
    """Token valido, pasa el gate de `mcp:access', pero sin
    `incidents:write' -- la tool (no el middleware HTTP) debe rechazar la
    llamada con el codigo documentado `missing_required_scope`."""

    token = dev_idp.issue_token(scopes=["mcp:access"])
    client = Client(running_server, auth=token)

    async with client:
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool(
                "create_incident_ticket_tool",
                {
                    "payload": {
                        "title": "x",
                        "description": "y",
                        "category": "lost_parcel",
                        "origin": "customer",
                        "branch": "la_warehouse",
                    }
                },
            )

        assert "missing_required_scope" in str(excinfo.value)


@pytest.mark.anyio
async def test_inventory_write_attempt_is_explicitly_rejected_end_to_end(running_server, dev_idp: DevIdP):
    token = dev_idp.issue_token(scopes=["mcp:access", "inventory:read"])
    client = Client(running_server, auth=token)

    async with client:
        result = await client.call_tool("update_inventory_stock_tool", {"payload": {"sku": "TEC-EAR-001", "quantity_delta": 5}})
        payload = result.structured_content
        assert payload["ok"] is False
        assert payload["error"] == "read_only_tool"
