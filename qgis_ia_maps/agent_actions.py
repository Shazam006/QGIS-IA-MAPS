"""Controlled non-Processing actions used by the QGIS AI agent.

All actions are explicit and auditable. No arbitrary Python execution is
provided. Destructive operations require an explicit confirmation flag.
"""

from pathlib import Path

from qgis.core import QgsProject, QgsVectorFileWriter


class AgentActions:
    def __init__(self, iface):
        self.iface = iface

    @staticmethod
    def _project():
        return QgsProject.instance()

    def _layer(self, layer_id):
        layer = self._project().mapLayer(str(layer_id))
        if layer is None:
            raise ValueError(f"Camada não encontrada: {layer_id}")
        return layer

    def set_visibility(self, layer_id, visible=True):
        layer = self._layer(layer_id)
        node = self._project().layerTreeRoot().findLayer(layer.id())
        if node is None:
            raise ValueError("Camada não encontrada na árvore do projeto.")
        node.setItemVisibilityChecked(bool(visible))
        return {"success": True, "layer_id": layer.id(), "visible": bool(visible)}

    def set_active_layer(self, layer_id):
        layer = self._layer(layer_id)
        self.iface.setActiveLayer(layer)
        return {"success": True, "layer_id": layer.id(), "name": layer.name()}

    def zoom_to_layer(self, layer_id):
        layer = self._layer(layer_id)
        self.iface.setActiveLayer(layer)
        self.iface.zoomToActiveLayer()
        return {"success": True, "layer_id": layer.id(), "name": layer.name()}

    def zoom_to_selection(self, layer_id):
        layer = self._layer(layer_id)
        self.iface.setActiveLayer(layer)
        if not hasattr(layer, "selectedFeatureCount") or layer.selectedFeatureCount() == 0:
            raise ValueError("A camada não possui feições selecionadas.")
        self.iface.mapCanvas().zoomToSelected(layer)
        return {"success": True, "layer_id": layer.id(), "selected": layer.selectedFeatureCount()}

    def clear_selection(self, layer_id):
        layer = self._layer(layer_id)
        if not hasattr(layer, "removeSelection"):
            raise ValueError("A camada não suporta seleção vetorial.")
        layer.removeSelection()
        return {"success": True, "layer_id": layer.id()}

    def remove_layer(self, layer_id, confirm=False):
        if not confirm:
            raise PermissionError("Remoção de camada exige confirm=true.")
        layer = self._layer(layer_id)
        name = layer.name()
        self._project().removeMapLayer(layer.id())
        return {"success": True, "removed_layer_id": layer_id, "name": name}

    def save_project(self, path=None):
        project = self._project()
        if path:
            project.setFileName(str(Path(path).expanduser()))
        if not project.write():
            raise RuntimeError("Falha ao salvar o projeto QGIS.")
        return {"success": True, "path": project.fileName()}

    def rename_layer_display(self, layer_id, name):
        layer = self._layer(layer_id)
        old_name = layer.name()
        layer.setName(str(name))
        return {"success": True, "layer_id": layer.id(), "old_name": old_name, "new_name": layer.name()}
