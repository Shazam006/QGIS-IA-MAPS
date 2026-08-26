"""QGIS-IA-MAPS MCP adapter.

This process exposes high-level cartographic tools through MCP and forwards
commands to the local QGIS plugin over its loopback JSON-lines bridge.

The server does not contain OpenAI credentials. Deployment behind HTTPS and
authentication is intentionally external to this package.
"""

import json
import os
import socket
from contextlib import closing

from mcp.server.fastmcp import FastMCP

HOST = os.getenv("QGIS_IA_MAPS_HOST", "127.0.0.1")
PORT = int(os.getenv("QGIS_IA_MAPS_PORT", "9877"))

mcp = FastMCP("QGIS-IA-MAPS")


def call_qgis(method, params=None):
    request = {"method": method, "params": params or {}}
    with closing(socket.create_connection((HOST, PORT), timeout=15)) as sock:
        sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    if not data:
        raise RuntimeError("QGIS-IA-MAPS não retornou resposta")
    response = json.loads(data.decode("utf-8"))
    if not response.get("ok"):
        raise RuntimeError(response.get("error", "Erro desconhecido no QGIS"))
    return response.get("result")


@mcp.tool()
def qgis_ping() -> dict:
    """Check whether the QGIS-IA-MAPS plugin is reachable."""
    return call_qgis("ping")


@mcp.tool()
def qgis_project_info() -> dict:
    """Return information about the current QGIS project."""
    return call_qgis("project.info")


@mcp.tool()
def qgis_list_layers() -> list:
    """List layers loaded in the current QGIS project."""
    return call_qgis("project.layers")


@mcp.tool()
def qgis_create_layout(name: str = "Mapa IA", page: str = "A4", orientation: str = "landscape") -> dict:
    """Create a map layout in QGIS."""
    return call_qgis("map.create_layout", {"name": name, "page": page, "orientation": orientation})


@mcp.tool()
def qgis_add_title(layout_name: str, text: str, size: float = 14, x: float = 20, y: float = 5) -> bool:
    """Add a title to a QGIS layout."""
    return call_qgis("map.add_title", {"layout_name": layout_name, "text": text, "size": size, "x": x, "y": y})


@mcp.tool()
def qgis_add_legend(layout_name: str, title: str = "Legenda", x: float = 220, y: float = 20) -> bool:
    """Add a legend to a QGIS layout."""
    return call_qgis("map.add_legend", {"layout_name": layout_name, "title": title, "x": x, "y": y})


@mcp.tool()
def qgis_add_scale(layout_name: str, x: float = 20, y: float = 185) -> bool:
    """Add a scale bar to a QGIS layout."""
    return call_qgis("map.add_scale", {"layout_name": layout_name, "x": x, "y": y})


@mcp.tool()
def qgis_export_map(layout_name: str, path: str, format: str = "pdf") -> bool:
    """Export a QGIS layout as PDF or PNG."""
    return call_qgis("map.export", {"layout_name": layout_name, "path": path, "format": format})


@mcp.tool()
def qgis_save_project(path: str | None = None) -> bool:
    """Save the current QGIS project, optionally changing its path."""
    return call_qgis("project.save", {"path": path})


if __name__ == "__main__":
    mcp.run()
