"""Structured QGIS project context for AI planning.

The context is intentionally compact: it describes the project, visible layers,
selection state and layer schemas without serialising whole datasets.
"""

from qgis.core import QgsMapLayer, QgsProject, QgsWkbTypes


class ProjectContextBuilder:
    def __init__(self, iface):
        self.iface = iface

    @staticmethod
    def _layer_kind(layer):
        if layer.type() == QgsMapLayer.VectorLayer:
            return "vector"
        if layer.type() == QgsMapLayer.RasterLayer:
            return "raster"
        return "other"

    def _layer_summary(self, layer, visible_ids, active_layer_id):
        result = {
            "id": layer.id(),
            "name": layer.name(),
            "type": self._layer_kind(layer),
            "visible": layer.id() in visible_ids,
            "active": layer.id() == active_layer_id,
            "crs": layer.crs().authid() if layer.crs().isValid() else None,
            "source": layer.source(),
        }

        if layer.type() == QgsMapLayer.VectorLayer:
            result.update({
                "geometry": QgsWkbTypes.displayString(layer.wkbType()),
                "feature_count": layer.featureCount(),
                "selected_feature_count": layer.selectedFeatureCount(),
                "fields": [
                    {"name": field.name(), "type": field.typeName()}
                    for field in layer.fields()
                ],
            })
        elif layer.type() == QgsMapLayer.RasterLayer:
            result.update({
                "band_count": layer.bandCount(),
                "width": layer.width(),
                "height": layer.height(),
                "pixel_size_x": layer.rasterUnitsPerPixelX(),
                "pixel_size_y": layer.rasterUnitsPerPixelY(),
            })
        return result

    def build(self):
        project = QgsProject.instance()
        visible_layers = list(self.iface.mapCanvas().layers())
        visible_ids = {layer.id() for layer in visible_layers}
        active = self.iface.activeLayer()
        active_id = active.id() if active else None

        layers = [
            self._layer_summary(layer, visible_ids, active_id)
            for layer in project.mapLayers().values()
        ]
        return {
            "project": {
                "path": project.fileName(),
                "title": project.title(),
                "crs": project.crs().authid() if project.crs().isValid() else None,
                "layer_count": len(layers),
                "visible_layer_count": len(visible_ids),
            },
            "active_layer_id": active_id,
            "layers": layers,
        }
