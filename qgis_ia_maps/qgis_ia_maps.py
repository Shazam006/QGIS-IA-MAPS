from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtWidgets import QAction, QDockWidget, QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit
from qgis.core import QgsProject, QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemScaleBar, QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes, QgsRectangle, QgsLayoutExporter


class QGISIAMaps(QObject):
    """Initial QGIS-IA-MAPS plugin shell.

    The first implementation keeps map automation inside PyQGIS. MCP transport is
    intentionally isolated from this controller so transport changes do not alter
    the cartographic logic.
    """

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.action = None
        self.dock = None
        self.status = None
        self.log = None

    def initGui(self):
        self.action = QAction("QGIS-IA-MAPS", self.iface.mainWindow())
        self.action.triggered.connect(self.show_dock)
        self.iface.addPluginToMenu("&QGIS-IA-MAPS", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
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
            self.dock.setWidget(panel)
            self.iface.addDockWidget(2, self.dock)
        self.dock.show()
        self.dock.raise_()

    def log_message(self, message):
        if self.log:
            self.log.append(message)

    def test_project(self):
        project = QgsProject.instance()
        self.status.setText("Status: projeto lido")
        self.log_message(f"Projeto: {project.fileName() or '(não salvo)'}")
        self.log_message(f"Camadas: {len(project.mapLayers())}")

    def project_info(self):
        project = QgsProject.instance()
        return {
            "path": project.fileName(),
            "title": project.title(),
            "layer_count": len(project.mapLayers()),
        }

    def list_layers(self):
        return [
            {
                "id": layer.id(),
                "name": layer.name(),
                "type": layer.type(),
                "source": layer.source(),
            }
            for layer in QgsProject.instance().mapLayers().values()
        ]

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
        layout.pageCollection().page(0).setPageSize(
            QgsLayoutSize(width, height, QgsUnitTypes.LayoutMillimeters)
        )
        project.layoutManager().addLayout(layout)

        map_item = QgsLayoutItemMap(layout)
        map_item.attemptSetSceneRect(20, 20, width - 40, height - 50)
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
                extent = QgsRectangle(current) if extent is None else QgsRectangle(extent)
                if extent != current:
                    extent.combineExtentWith(current)
            if extent:
                extent.scale(1.10)
                map_item.setExtent(extent)

        layout.addLayoutItem(map_item)
        return {"name": name, "page": page, "orientation": orientation}

    def add_title(self, layout_name, text, size=14, x=20, y=5):
        layout = QgsProject.instance().layoutManager().layoutByName(layout_name)
        if not layout:
            raise ValueError(f"Layout não encontrado: {layout_name}")
        label = QgsLayoutItemLabel(layout)
        label.setText(text)
        label.setFontPointSize(float(size))
        label.adjustSizeToText()
        label.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(label)
        return True

    def add_legend(self, layout_name, title="Legenda", x=220, y=20):
        layout = QgsProject.instance().layoutManager().layoutByName(layout_name)
        if not layout:
            raise ValueError(f"Layout não encontrado: {layout_name}")
        legend = QgsLayoutItemLegend(layout)
        legend.setTitle(title)
        legend.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(legend)
        return True

    def add_scale(self, layout_name, x=20, y=185):
        layout = QgsProject.instance().layoutManager().layoutByName(layout_name)
        if not layout:
            raise ValueError(f"Layout não encontrado: {layout_name}")
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
        layout = QgsProject.instance().layoutManager().layoutByName(layout_name)
        if not layout:
            raise ValueError(f"Layout não encontrado: {layout_name}")
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
