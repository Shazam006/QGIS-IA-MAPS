"""Local execution gateway for QGIS-IA-MAPS.

The bridge exposes a controlled JSON-lines API over loopback. Worker threads
never touch PyQGIS directly: every request is marshalled to the QGIS main
thread. Arbitrary Python execution is intentionally not supported.
"""

import json
import socket
import threading

from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot

from .agent_actions import AgentActions
from .capabilities import CapabilityRegistry
from .processing_executor import ProcessingExecutor
from .project_context import ProjectContextBuilder


class MCPBridge(QObject):
    _request_signal = pyqtSignal(object)

    def __init__(self, controller, host="127.0.0.1", port=9877):
        super().__init__()
        self.controller = controller
        self.host = host
        self.port = int(port)
        self._server = None
        self._thread = None
        self._stop = threading.Event()
        self._request_signal.connect(self._process_request)

        iface = controller.iface
        self.capabilities = CapabilityRegistry()
        self.context_builder = ProjectContextBuilder(iface)
        self.processing = ProcessingExecutor(iface)
        self.actions = AgentActions(iface)

    @property
    def running(self):
        return self._server is not None

    def start(self):
        if self.running:
            return
        self._stop.clear()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(5)
        server.settimeout(0.5)
        self._server = server
        self._thread = threading.Thread(target=self._serve, args=(server,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        server = self._server
        self._server = None
        if server:
            try:
                server.close()
            except OSError:
                pass

    def _serve(self, server):
        while not self._stop.is_set():
            try:
                conn, _ = server.accept()
            except (socket.timeout, OSError):
                continue
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        with conn:
            file = conn.makefile("rwb")
            while not self._stop.is_set():
                raw = file.readline(1024 * 1024)
                if not raw:
                    break
                if len(raw) > 1024 * 1024:
                    self._write(file, {"ok": False, "error": "Request too large"})
                    break
                try:
                    request = json.loads(raw.decode("utf-8"))
                    response = self._dispatch_on_main_thread(request)
                except Exception as exc:
                    response = {"ok": False, "error": str(exc)}
                self._write(file, response)

    @staticmethod
    def _write(file, response):
        payload = json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n"
        file.write(payload.encode("utf-8"))
        file.flush()

    def _dispatch_on_main_thread(self, request):
        context = {"request": request, "event": threading.Event(), "response": None}
        self._request_signal.emit(context)
        if not context["event"].wait(60.0):
            raise TimeoutError("QGIS did not process the request within 60 seconds")
        if context["response"] is None:
            raise RuntimeError("QGIS returned no response")
        return context["response"]

    @pyqtSlot(object)
    def _process_request(self, context):
        try:
            context["response"] = self.dispatch(context["request"])
        except Exception as exc:
            context["response"] = {"ok": False, "error": str(exc)}
        finally:
            context["event"].set()

    def dispatch(self, request):
        if not isinstance(request, dict):
            raise ValueError("Request must be a JSON object")
        method = request.get("method")
        params = request.get("params") or {}
        if not isinstance(params, dict):
            raise ValueError("params must be a JSON object")

        # Discovery and project awareness.
        if method == "ping":
            return {"ok": True, "result": {"pong": True, "mode": "agentic-qgis"}}
        if method == "capabilities.list":
            return {"ok": True, "result": self.capabilities.snapshot()}
        if method == "processing.providers":
            return {"ok": True, "result": self.capabilities.providers()}
        if method == "processing.algorithms":
            return {"ok": True, "result": self.capabilities.algorithms(**params)}
        if method == "processing.describe":
            return {"ok": True, "result": self.capabilities.describe(**params)}
        if method == "project.context":
            return {"ok": True, "result": self.context_builder.build()}
        if method == "project.info":
            return {"ok": True, "result": self.controller.project_info()}
        if method == "project.layers":
            return {"ok": True, "result": self.controller.list_layers()}

        # Generic QGIS Processing execution.
        if method == "processing.validate":
            return {"ok": True, "result": self.processing.validate(**params)}
        if method == "processing.run":
            return {"ok": True, "result": self.processing.run(**params)}

        # Controlled non-Processing actions.
        if method == "layer.set_visibility":
            return {"ok": True, "result": self.actions.set_visibility(**params)}
        if method == "layer.set_active":
            return {"ok": True, "result": self.actions.set_active_layer(**params)}
        if method == "layer.zoom":
            return {"ok": True, "result": self.actions.zoom_to_layer(**params)}
        if method == "layer.zoom_selection":
            return {"ok": True, "result": self.actions.zoom_to_selection(**params)}
        if method == "selection.clear":
            return {"ok": True, "result": self.actions.clear_selection(**params)}
        if method == "layer.remove":
            return {"ok": True, "result": self.actions.remove_layer(**params)}
        if method == "layer.rename":
            return {"ok": True, "result": self.actions.rename_layer_display(**params)}
        if method == "project.save":
            return {"ok": True, "result": self.actions.save_project(**params)}

        # Existing cartographic commands remain available as one module among many.
        if method == "map.create_layout":
            return {"ok": True, "result": self.controller.create_layout(**params)}
        if method == "map.add_title":
            return {"ok": True, "result": self.controller.add_title(**params)}
        if method == "map.add_legend":
            return {"ok": True, "result": self.controller.add_legend(**params)}
        if method == "map.add_scale":
            return {"ok": True, "result": self.controller.add_scale(**params)}
        if method == "map.export":
            return {"ok": True, "result": self.controller.export_layout(**params)}

        raise ValueError(f"Método não suportado: {method}")
