"""QGIS-IA-MAPS MCP adapter.

This server exposes the current QGIS installation as a controlled tool surface
for GPT. It forwards structured requests to the local QGIS-IA-MAPS bridge.
No OpenAI credentials are stored here and arbitrary Python execution is not
exposed.
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
    with closing(socket.create_connection((HOST, PORT), timeout=30)) as sock:
        sock.sendall((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
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
    """Check whether the QGIS-IA-MAPS agent bridge is reachable."""
    return call_qgis("ping")


@mcp.tool()
def qgis_context() -> dict:
    """Return compact structured context for the currently open QGIS project."""
    return call_qgis("project.context")


@mcp.tool()
def qgis_capabilities() -> dict:
    """Return installed QGIS providers and available high-level capability groups."""
    return call_qgis("capabilities.list")


@mcp.tool()
def qgis_processing_providers() -> list:
    """List Processing providers available in this QGIS installation."""
    return call_qgis("processing.providers")


@mcp.tool()
def qgis_processing_algorithms(provider_id: str | None = None, search: str | None = None, limit: int = 200) -> list:
    """Search algorithms registered in the local QGIS Processing registry."""
    return call_qgis("processing.algorithms", {"provider_id": provider_id, "search": search, "limit": limit})


@mcp.tool()
def qgis_processing_describe(algorithm_id: str) -> dict:
    """Describe one Processing algorithm, including parameters and outputs."""
    return call_qgis("processing.describe", {"algorithm_id": algorithm_id})


@mcp.tool()
def qgis_processing_validate(algorithm_id: str, parameters: dict) -> dict:
    """Validate a planned Processing call before execution."""
    return call_qgis("processing.validate", {"algorithm_id": algorithm_id, "parameters": parameters})


@mcp.tool()
def qgis_processing_run(algorithm_id: str, parameters: dict, add_outputs_to_project: bool = True) -> dict:
    """Run a registered QGIS Processing algorithm with validated parameters."""
    return call_qgis("processing.run", {
        "algorithm_id": algorithm_id,
        "parameters": parameters,
        "add_outputs_to_project": add_outputs_to_project,
    })


@mcp.tool()
def qgis_set_layer_visibility(layer_id: str, visible: bool = True) -> dict:
    """Show or hide a layer in the current QGIS project."""
    return call_qgis("layer.set_visibility", {"layer_id": layer_id, "visible": visible})


@mcp.tool()
def qgis_set_active_layer(layer_id: str) -> dict:
    """Set the active QGIS layer."""
    return call_qgis("layer.set_active", {"layer_id": layer_id})


@mcp.tool()
def qgis_zoom_to_layer(layer_id: str) -> dict:
    """Zoom the QGIS canvas to a layer."""
    return call_qgis("layer.zoom", {"layer_id": layer_id})


@mcp.tool()
def qgis_zoom_to_selection(layer_id: str) -> dict:
    """Zoom the QGIS canvas to selected features in a layer."""
    return call_qgis("layer.zoom_selection", {"layer_id": layer_id})


@mcp.tool()
def qgis_clear_selection(layer_id: str) -> dict:
    """Clear the selection of a vector layer."""
    return call_qgis("selection.clear", {"layer_id": layer_id})


@mcp.tool()
def qgis_remove_layer(layer_id: str, confirm: bool = False) -> dict:
    """Remove a layer from the project. Destructive: confirm must be true."""
    return call_qgis("layer.remove", {"layer_id": layer_id, "confirm": confirm})


@mcp.tool()
def qgis_save_project(path: str | None = None) -> dict:
    """Save the current QGIS project, optionally to a new path."""
    return call_qgis("project.save", {"path": path})


# Cartographic functions remain available, but are only one module of the agent.
@mcp.tool()
def qgis_create_layout(name: str = "Mapa IA", page: str = "A4", orientation: str = "landscape") -> dict:
    return call_qgis("map.create_layout", {"name": name, "page": page, "orientation": orientation})


@mcp.tool()
def qgis_export_map(name: str, path: str, format: str = "pdf") -> dict:
    return call_qgis("map.export", {"name": name, "path": path, "format": format})


def main():
    mcp.run()


if __name__ == "__main__":
    main()
