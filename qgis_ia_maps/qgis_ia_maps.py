from pathlib import Path

from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtWidgets import (
    QAction,
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
)
from qgis.core import (
    QgsProject,
    QgsPrintLayout,
    QgsLayoutItemMap,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsUnitTypes,
    QgsLayoutExporter,
    QgsLayerTree,
    QgsWkbTypes,
)

from .legend_naming import classify_layer, is_legend_candidate, title_from_name
from .mcp_bridge import MCPBridge


class QGISIAMaps(QObject):
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
            self.dock.deleteLater()
            self.dock = None

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

            map_button = QPushButton("Criar mapa A4")
            map_button.clicked.connect(self.create_a4_map)
            layout.addWidget(map_button)

            bridge_button = QPushButton("Iniciar ponte local")
            bridge_button.clicked.connect(self.toggle_bridge)
            layout.addWidget(bridge_button)

            self.dock.setWidget(panel)
            self.iface.addDockWidget(2, self.dock)

        self.dock.show()
        self.dock.raise_()

    def log_message(self, message):
        if self.log:
            self.log.append(str(message))

    def toggle_bridge(self):
        if self.bridge.running:
            self.bridge.stop()
            self.status.setText("Status: ponte parada")
            self.log_message("Ponte local parada.")
            return
        try:
            self.bridge.start()
            self.status.setText(
                f"Status: ponte local em {self.bridge.host}:{self.bridge.port}"
            )
            self.log_message(
                f"Ponte local iniciada em {self.bridge.host}:{self.bridge.port}."
            )
        except Exception as exc:
            self.status.setText("Status: erro ao iniciar ponte")
            self.log_message(f"Erro: {exc}")

    def test_project(self):
        try:
            info = self.project_info()
            self.status.setText("Status: projeto lido")
            self.log_message(f"Projeto: {info['path'] or '(não salvo)'}")
            self.log_message(f"Camadas: {info['layer_count']}")
            for layer in self.list_layers():
                marker = "ATIVA" if layer["visible"] else "oculta"
                self.log_message(f"- {layer['name']} [{marker}] ({layer['type']})")
        except Exception as exc:
            self.status.setText("Status: erro")
            self.log_message(f"ERRO: {exc}")

    def project_info(self):
        project = QgsProject.instance()
        return {
            "path": project.fileName(),
            "title": project.title(),
            "layer_count": len(project.mapLayers()),
            "crs": project.crs().authid(),
        }

    def list_layers(self):
        root = QgsProject.instance().layerTreeRoot()
        result = []
        active = self._visible_canvas_layers()
        active_ids = {layer.id() for layer in active}
        for layer in QgsProject.instance().mapLayers().values():
            node = root.findLayer(layer.id())
            result.append(
                {
                    "id": layer.id(),
                    "name": layer.name(),
                    "type": layer.type(),
                    "source": layer.source(),
                    "visible": bool(node and node.isVisible()),
                    "active_in_canvas": layer.id() in active_ids,
                    "crs": layer.crs().authid() if layer.crs().isValid() else None,
                    "legend_name": title_from_name(layer.name()),
                    "classification": classify_layer(layer),
                }
            )
        return result

    def _visible_canvas_layers(self):
        """Return layers currently displayed by the QGIS map canvas."""
        return list(self.iface.mapCanvas().layers())

    def _legend_tree_for_active_layers(self):
        """Build a temporary legend tree without changing project layer names."""
        project = QgsProject.instance()
        canvas_layers = self._visible_canvas_layers()
        active_ids = {layer.id() for layer in canvas_layers}

        root = project.layerTreeRoot().clone()
        for node in list(root.findLayers()):
            layer = node.layer()
            keep = (
                layer is not None
                and layer.id() in active_ids
                and is_legend_candidate(layer)
            )
            if not keep:
                parent = node.parent()
                if parent is not None and QgsLayerTree.isGroup(parent):
                    QgsLayerTree.toGroup(parent).removeChildNode(node)
                continue

            node.setName(title_from_name(layer.name()))
            node.setUseLayerName(False)

        root.removeChildrenGroupWithoutLayers()
        return root

    def _polygon_layer_count(self):
        """Count active polygon layers which are eligible for the legend."""
        return sum(
            1
            for layer in self._visible_canvas_layers()
            if is_legend_candidate(layer)
            and layer.type() == QgsWkbTypes.VectorGeometry
            and layer.geometryType() == QgsWkbTypes.PolygonGeometry
        )

    def _legend_symbol_size(self):
        """Choose polygon swatch size from the number of active polygons.

        Up to four active polygon layers: 8 x 4 mm.
        More than four active polygon layers: 4 x 2 mm.
        """
        polygon_count = self._polygon_layer_count()
        if polygon_count <= 4:
            return 8.0, 4.0, polygon_count
        return 4.0, 2.0, polygon_count

    def create_layout(self, name="Mapa IA", page="A4", orientation="landscape"):
        project = QgsProject.instance()
        old = project.layoutManager().layoutByName(name)
        if old:
            project.layoutManager().removeLayout(old)

        page_key = page.upper()
        if page_key not in {"A4", "A3"}:
            raise ValueError("page deve ser A4 ou A3")
        sizes = {"A4": (297, 210), "A3": (420, 297)}
        width, height = sizes[page_key]
        if orientation.lower() == "portrait":
            width, height = height, width
        elif orientation.lower() != "landscape":
            raise ValueError("orientation deve ser landscape ou portrait")

        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName(name)
        layout.pageCollection().page(0).setPageSize(
            QgsLayoutSize(width, height, QgsUnitTypes.LayoutMillimeters)
        )
        project.layoutManager().addLayout(layout)

        map_item = QgsLayoutItemMap(layout)
        map_item.attemptMove(QgsLayoutPoint(10, 18, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(
            QgsLayoutSize(width - 80, height - 48, QgsUnitTypes.LayoutMillimeters)
        )
        map_item.setFrameEnabled(True)

        layers = self._visible_canvas_layers()
        if layers:
            map_item.setLayers(layers)
            canvas_extent = self.iface.mapCanvas().extent()
            if not canvas_extent.isEmpty():
                canvas_extent.scale(1.05)
                map_item.setExtent(canvas_extent)

        layout.addLayoutItem(map_item)
        return {"name": name, "page": page_key, "orientation": orientation.lower()}

    def _layout(self, name):
        layout = QgsProject.instance().layoutManager().layoutByName(name)
        if not layout:
            raise ValueError(f"Layout não encontrado: {name}")
        return layout

    def _first_map(self, layout):
        maps = [item for item in layout.items() if isinstance(item, QgsLayoutItemMap)]
        if not maps:
            raise ValueError("O layout não possui item de mapa")
        return maps[0]

    def add_title(self, layout_name, text, size=14, x=10, y=5):
        layout = self._layout(layout_name)
        item = QgsLayoutItemLabel(layout)
        item.setText(str(text))
        item.setFontPointSize(float(size))
        item.adjustSizeToText()
        item.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(item)
        return True

    def add_legend(self, layout_name, title="Legenda", x=225, y=18):
        layout = self._layout(layout_name)
        legend = QgsLayoutItemLegend(layout)
        legend.setTitle(str(title))
        legend.setLinkedMap(self._first_map(layout))
        legend.setAutoUpdateModel(False)
        legend.model().setRootGroup(self._legend_tree_for_active_layers())

        symbol_width, symbol_height, polygon_count = self._legend_symbol_size()
        legend.setSymbolWidth(symbol_width)
        legend.setSymbolHeight(symbol_height)

        legend.refresh()
        legend.adjustBoxSize()
        legend.attemptMove(
            QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters)
        )
        return {
            "success": True,
            "polygon_layer_count": polygon_count,
            "symbol_size_mm": {
                "width": symbol_width,
                "height": symbol_height,
            },
            "layers": [
                {
                    "original_name": layer.name(),
                    "legend_name": title_from_name(layer.name()),
                }
                for layer in self._visible_canvas_layers()
                if is_legend_candidate(layer)
            ],
        }

    def add_scale(self, layout_name, x=10, y=185):
        layout = self._layout(layout_name)
        scale = QgsLayoutItemScaleBar(layout)
        scale.setStyle("Single Box")
        scale.setUnits(QgsUnitTypes.DistanceMeters)
        scale.setNumberOfSegments(4)
        scale.setNumberOfSegmentsLeft(0)
        scale.setLinkedMap(self._first_map(layout))
        scale.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(scale)
        return True

    def export_layout(self, layout_name, path, format="pdf"):
        layout = self._layout(layout_name)
        output = Path(path).expanduser()
        if not output.parent.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
        fmt = str(format).lower()
        exporter = QgsLayoutExporter(layout)
        if fmt == "png":
            result = exporter.exportToImage(str(output), QgsLayoutExporter.ImageExportSettings())
        elif fmt == "pdf":
            result = exporter.exportToPdf(str(output), QgsLayoutExporter.PdfExportSettings())
        else:
            raise ValueError("format deve ser pdf ou png")
        if result != QgsLayoutExporter.Success:
            raise RuntimeError(f"Falha ao exportar {fmt}: código {int(result)}")
        return {"success": True, "path": str(output)}

    def save_project(self, path=None):
        project = QgsProject.instance()
        if path:
            project.setFileName(str(Path(path).expanduser()))
        if not project.write():
            raise RuntimeError("QGIS não conseguiu salvar o projeto")
        return {"success": True, "path": project.fileName()}
