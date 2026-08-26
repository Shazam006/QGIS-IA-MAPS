"""Local bridge between the QGIS plugin and an external MCP process.

The socket listener runs in worker threads, but every PyQGIS operation is
marshalled back to the QGIS main thread before it touches QgsProject, layouts,
or other QGIS/Qt objects.

The bridge binds to loopback only and uses a small JSON-lines protocol. It is
not itself a full MCP transport. A separate MCP adapter can wrap this bridge.
No OpenAI credentials are stored in the plugin.
"""

import json
import socket
import threading

from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot


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
        context = {
            "request": request,
            "event": threading.Event(),
            "response": None,
        }
        self._request_signal.emit(context)
        if not context["event"].wait(30.0):
            raise TimeoutError("QGIS did not process the request within 30 seconds")
        response = context["response"]
        if response is None:
            raise RuntimeError("QGIS returned no response")
        return response

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

        if method == "ping":
            return {"ok": True, "result": {"pong": True}}
        if method == "project.info":
            return {"ok": True, "result": self.controller.project_info()}
        if method == "project.layers":
            return {"ok": True, "result": self.controller.list_layers()}
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
        if method == "project.save":
            return {"ok": True, "result": self.controller.save_project(**params)}

        raise ValueError(f"Método não suportado: {method}")
