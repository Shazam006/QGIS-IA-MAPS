"""Local bridge between the QGIS plugin and an external MCP process.

The bridge deliberately binds to loopback only. It is a small JSON-lines
protocol intended to be replaced or wrapped by a proper MCP transport later.
No OpenAI credentials are stored in this plugin.
"""

import json
import socket
import threading


class MCPBridge:
    def __init__(self, controller, host="127.0.0.1", port=9877):
        self.controller = controller
        self.host = host
        self.port = int(port)
        self._server = None
        self._thread = None
        self._stop = threading.Event()

    @property
    def running(self):
        return self._server is not None

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(5)
        self._server.settimeout(0.5)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
        self._server = None

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except (socket.timeout, OSError):
                continue
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        with conn:
            file = conn.makefile("rwb")
            for raw in file:
                try:
                    request = json.loads(raw.decode("utf-8"))
                    response = self.dispatch(request)
                except Exception as exc:
                    response = {"ok": False, "error": str(exc)}
                file.write((json.dumps(response) + "\n").encode("utf-8"))
                file.flush()

    def dispatch(self, request):
        method = request.get("method")
        params = request.get("params") or {}

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
