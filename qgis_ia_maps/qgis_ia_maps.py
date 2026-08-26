from qgis.PyQt.QtCore import QObject, QRectF
from qgis.PyQt.QtWidgets import QAction, QDockWidget, QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit
from qgis.core import QgsProject, QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemScaleBar, QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes, QgsRectangle, QgsLayoutExporter

from .mcp_bridge import MCPBridge


class QGISIAMaps(QObject):
    """QGIS-facing controller for QGIS-IA-MAPS."""

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.action = None
        self.dock = None
        self.status = None
        self.log = None
        self.bridge = MCPBridge(self)

    def initGui(self):
        self.action = QAction("QGIS-IA-MAPS", self.iface.mainWindow())
        self.action.triggered.connect(self.show_dock)
        self.iface.addPluginToMenu("&QGIS-IA-MAPS", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.bridge.stop()
        if self.action:
            self.iface.removePluginMenu("&QGIS-IA-MAPS", self.action)
            self.iface.removeToolBarIcon(self.action)
        if self.dock:
            self.iface.removeDockWidget(self.dock)

    def show_dock(self):
        if self.dock is None:
            self.dock = QDockWidget("QGIS-IA-MAPS", self.iface.mainWindow())
            panel = QWidget()
            layout = QVBoxLayout(panel)
            layout.addWidget(QLabel("Automação cartográfica e geração de mapas"))
            self.status = QLabel("Status: pronto")
            layout.addWidget(self.status)
            self.log = QTextEdit()
            self.log.setReadOnly(True)
            layout.addWidget(self.log)
            test_button = QPushButton("Testar projeto atual")
            test_button.clicked.connect(self.test_project)
            layout.addWidget(test_button)
            bridge_button = QPushButton("Iniciar ponte local (MCP)")
            bridge_button.clicked.connect(self.toggle_bridge)
            layout.addWidget(bridge_button)
            self.dock.setWidget(panel)
            self.iface.addDockWidget(2, self.dock)
        self.dock.show()
        self.dock.raise_()

    def log_message(self, message):
        if self.log:
            self.log.append(message)

    def toggle_bridge(self):
        if self.bridge.running:
            self.bridge.stop()
            self.status.setText("Status: ponte parada")
            self.log_message("Ponte local parada.")
            return
        try:
            self.bridge.start()
            self.status.setText(f"Status: MCP local em {self.bridge.host}:{self.bridge.port}")
            self.log_message(f"Ponte local iniciada em {self.bridge.host}:{self.bridge.port}.")
        except Exception as exc:
            self.status.setText("Status: erro ao iniciar MCP")
            self.log_message(f"Erro: {exc}")

    def test_project(self):
        info = self.project_info()
        self.status.setText("Status: projeto lido")
        self.log_message(f"Projeto: {info['path'] or '(não salvo)'}")
        self.log_message(f"Camadas: {info['layer_count']}")

    def project_info(self):
        project = QgsProject.instance()
        return {"path": project.fileName(), "title": project.title(), "layer_count": len(project.mapLayers())}

    def list_layers(self):
        return [{"id": l.id(), "name": l.name(), "type": l.type(), "source": l.source()} for l in QgsProject.instance().mapLayers().values()]

    def create_layout(self, name="Mapa IA", page="A4", orientation="landscape"):
        project = QgsProject.instance()
        old = project.layoutManager().layoutByName(name)
        if old:
            project.layoutManager().removeLayout(old)
        sizes = {"A4": (297, 210), "A3": (420, 297)}
        width, height = sizes.get(page.upper(), sizes["A4"])
        if orientation.lower() == "portrait":
            width, height = height, width
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName(name)
        layout.pageCollection().page(0).setPageSize(QgsLayoutSize(width, height, QgsUnitTypes.LayoutMillimeters))
        project.layoutManager().addLayout(layout)
        map_item = QgsLayoutItemMap(layout)
        map_item.setRect(QRectF(20.0, 20.0, float(width - 40), float(height - 50)))
        map_item.setFrameEnabled(True)
        layers = list(project.mapLayers().values())
        if layers:
            map_item.setLayers(layers)
            extent = None
            for layer in layers:
                if not hasattr(layer, "extent"):
                    continue
                current = layer.extent()
                if current.isEmpty():
                    continue
                if extent is None:
                    extent = QgsRectangle(current)
                else:
                    extent.combineExtentWith(current)
            if extent:
                extent.scale(1.10)
                map_item.setExtent(extent)
        layout.addLayoutItem(map_item)
        return {"name": name, "page": page, "orientation": orientation}

    def _layout(self, name):
        layout = QgsProject.instance().layoutManager().layoutByName(name)
        if not layout:
            raise ValueError(f"Layout não encontrado: {name}")
        return layout

    def add_title(self, layout_name, text, size=14, x=20, y=5):
        layout = self._layout(layout_name)
        label = QgsLayoutItemLabel(layout)
        label.setText(text)
        label.setFontPointSize(float(size))
        label.adjustSizeToText()
        label.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(label)
        return True

    def add_legend(self, layout_name, title="Legenda", x=220, y=20):
        layout = self._layout(layout_name)
        legend = QgsLayoutItemLegend(layout)
        legend.setTitle(title)
        legend.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(legend)
        return True

    def add_scale(self, layout_name, x=20, y=185):
        layout = self._layout(layout_name)
        maps = [item for item in layout.items() if isinstance(item, QgsLayoutItemMap)]
        if not maps:
            raise ValueError("O layout não possui item de mapa")
        scale = QgsLayoutItemScaleBar(layout)
        scale.setStyle("Single Box")
        scale.setUnits(QgsUnitTypes.DistanceMeters)
        scale.setNumberOfSegments(4)
        scale.setNumberOfSegmentsLeft(0)
        scale.setLinkedMap(maps[0])
        scale.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(scale)
        return True

    def export_layout(self, layout_name, path, format="pdf"):
        layout = self._layout(layout_name)
        exporter = QgsLayoutExporter(layout)
        if format.lower() == "png":
            result = exporter.exportToImage(path, QgsLayoutExporter.ImageExportSettings())
        else:
            result = exporter.exportToPdf(path, QgsLayoutExporter.PdfExportSettings())
        return result == QgsLayoutExporter.Success

    def save_project(self, path=None):
        project = QgsProject.instance()
        if path:
            project.setFileName(path)
        return project.write()
