"""Manage the user's standard QGIS QPT template without changing the source file."""

from pathlib import Path
import re

from qgis.PyQt.QtXml import QDomDocument
from qgis.core import QgsPrintLayout, QgsProject, QgsLayoutItemLabel, QgsLayoutItemMap, QgsLayoutItemLegend, QgsLayoutItemScaleBar


DEFAULT_TEMPLATE = "Imagens de Satelite.qpt"


def _norm(value):
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9áéíóúãõç ]+", " ", text)


class TemplateManager:
    def __init__(self, iface, controller):
        self.iface = iface
        self.controller = controller

    def template_path(self):
        candidates = [
            Path(__file__).resolve().parent / "templates" / DEFAULT_TEMPLATE,
            Path(__file__).resolve().parent.parent / "templates" / DEFAULT_TEMPLATE,
        ]
        for path in candidates:
            if path.exists():
                return path
        return None

    def load_template(self, layout_name="Mapa IA"):
        path = self.template_path()
        if path is None:
            raise FileNotFoundError(f"Template padrão não encontrado: {DEFAULT_TEMPLATE}")
        project = QgsProject.instance()
        old = project.layoutManager().layoutByName(layout_name)
        if old:
            project.layoutManager().removeLayout(old)

        document = QDomDocument()
        if not document.setContent(path.read_text(encoding="utf-8")):
            raise ValueError("Não foi possível ler o QPT padrão.")
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName(layout_name)
        context = project.createExpressionContext()
        if not layout.readXml(document.documentElement(), document, context):
            raise ValueError("Não foi possível importar o QPT para o projeto QGIS.")
        layout.setName(layout_name)
        project.layoutManager().addLayout(layout)
        return layout

    @staticmethod
    def items(layout):
        return list(layout.items())

    @staticmethod
    def find_label(layout, *names):
        wanted = {_norm(name) for name in names}
        for item in layout.items():
            if not isinstance(item, QgsLayoutItemLabel):
                continue
            item_name = _norm(item.displayName())
            text = _norm(item.text())
            if item_name in wanted or text in wanted:
                return item
            if any(name in item_name or name in text for name in wanted):
                return item
        return None

    @staticmethod
    def find_map(layout, *names):
        for item in layout.items():
            if not isinstance(item, QgsLayoutItemMap):
                continue
            if not names:
                return item
            hay = _norm(item.displayName())
            if any(_norm(name) in hay for name in names):
                return item
        return None

    def populate(self, layout, title=None, description=None, owner=None, municipality=None, area=None, date=None, crs=None):
        replacements = {
            "title": title,
            "description": description,
            "owner": owner,
            "municipality": municipality,
            "area": area,
            "date": date,
            "crs": crs,
        }
        aliases = {
            "title": ("imagem de satélite", "imagem de satelite", "planta planimetrica", "título", "titulo"),
            "description": ("descrição", "descricao"),
            "owner": ("proprietário", "proprietario"),
            "municipality": ("município", "municipio"),
            "area": ("área", "area"),
            "date": ("data",),
            "crs": ("src", "sistema de referência", "sistema de referencia"),
        }
        updated = {}
        for key, value in replacements.items():
            if value in (None, ""):
                continue
            item = self.find_label(layout, *aliases[key])
            if item:
                item.setText(str(value))
                item.adjustSizeToText()
                updated[key] = item.displayName()
        return updated

    def bind_active_layers(self, layout):
        map_item = self.find_map(layout, "mapa 2", "mapa", "planta") or self.find_map(layout)
        if map_item is None:
            raise ValueError("Não foi encontrado item de mapa no template QPT.")
        layers = list(self.iface.mapCanvas().layers())
        if layers:
            map_item.setLayers(layers)
            extent = self.iface.mapCanvas().extent()
            if not extent.isEmpty():
                extent.scale(1.05)
                map_item.setExtent(extent)
        return map_item

    def update_legend(self, layout):
        legends = [item for item in layout.items() if isinstance(item, QgsLayoutItemLegend)]
        if not legends:
            return None
        # Keep the template's typography and frame. Only replace the model's
        # content through the existing legend API.
        legend = legends[0]
        legend.setAutoUpdateModel(False)
        legend.model().setRootGroup(self.controller._legend_tree_for_active_layers())
        width, height, count = self.controller._legend_symbol_size()
        legend.setSymbolWidth(width)
        legend.setSymbolHeight(height)
        legend.refresh()
        legend.adjustBoxSize()
        return {"polygon_layer_count": count, "symbol_size_mm": {"width": width, "height": height}}
