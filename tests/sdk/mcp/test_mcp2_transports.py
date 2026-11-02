"""MCP2 wire and credential-boundary regression tests."""

import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import uvicorn
from fastmcp import FastMCP

from openhands.sdk.mcp import create_mcp_tools
from openhands.sdk.mcp.config import coerce_mcp_config
from openhands.sdk.mcp.utils import _origin_bound_client_factory


server = FastMCP("addition")


@server.tool()
def add(a: int, b: int) -> int:
    return a + b


def _call_add(config):
    with create_mcp_tools(coerce_mcp_config({"addition": config}), timeout=10) as client:
        tool = next(tool for tool in client if tool.name == "add")
        for _ in range(2):
            result = tool(tool.action_from_arguments({"a": 19, "b": 23}))
            assert not result.is_error
            assert "42" in result.text


def test_stdio_add():
    script = Path(__file__).with_name("add_stdio_server.py")
    _call_add({"transport": "stdio", "command": sys.executable, "args": [str(script)]})


def test_streamable_http_add():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    uv = uvicorn.Server(uvicorn.Config(server.http_app(path="/mcp"), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not uv.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert uv.started
        _call_add({"transport": "http", "url": f"http://127.0.0.1:{port}/mcp"})
    finally:
        uv.should_exit = True
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_off_origin_redirect_strips_authorization():
    received = []

    class Destination(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    destination = ThreadingHTTPServer(("127.0.0.1", 0), Destination)

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers.get("Authorization") == "Bearer secret"
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{destination.server_port}/destination")
            self.end_headers()

        def log_message(self, *args):
            pass

    origin = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (origin, destination)]
    for thread in threads:
        thread.start()
    try:
        url = f"http://127.0.0.1:{origin.server_port}/mcp"
        factory = _origin_bound_client_factory(url, ("Authorization",))
        async with factory(headers={"Authorization": "Bearer secret"}) as client:
            response = await client.get(url, follow_redirects=True)
        assert response.status_code == 200
        assert received == [None]
    finally:
        for http_server in (origin, destination):
            http_server.shutdown()
            http_server.server_close()
        for thread in threads:
            thread.join(timeout=5)
