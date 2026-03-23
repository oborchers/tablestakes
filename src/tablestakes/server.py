"""FastMCP server instance and tool registration."""

from fastmcp import FastMCP

mcp = FastMCP("tablestakes")

# Tool imports trigger registration via @mcp.tool decorators.
from tablestakes.tools import column as _column  # noqa: F401, E402
from tablestakes.tools import read as _read  # noqa: F401, E402
from tablestakes.tools import write as _write  # noqa: F401, E402
