"""Entry point for running the MCP server via stdio transport."""

from scanbox.mcp.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
