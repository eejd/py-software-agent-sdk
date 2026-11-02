"""Real MCP stdio server for transport integration tests."""

from fastmcp import FastMCP

server = FastMCP("addition")


@server.tool()
def add(a: int, b: int) -> int:
    return a + b


if __name__ == "__main__":
    server.run(transport="stdio", show_banner=False)
