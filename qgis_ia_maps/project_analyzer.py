"""Build a structured, AI-ready description of the active QGIS project."""

from .layer_analyzer import analyze_layer
from .legend_naming import classify_layer, is_legend_candidate, title_from_name
from .zoning import find_object_layer, find_zoning_layer


class ProjectAnalyzer:
    def __init__(self, controller):
        self.controller = controller

    def analyze(self):
        canvas_layers = list(self.controller.iface.mapCanvas().layers())
        active = []
        for layer in canvas_layers:
            item = analyze_layer(layer)
            item.update({
                "id": layer.id(),
                "visible": True,
                "active_in_canvas": True,
                "legend_name": title_from_name(layer.name()),
                "classification": classify_layer(layer),
                "legend_candidate": is_legend_candidate(layer),
                "selected_feature_count": layer.selectedFeatureCount() if hasattr(layer, "selectedFeatureCount") else 0,
            })
            active.append(item)

        object_layer = find_object_layer(canvas_layers, self.controller.iface.activeLayer())
        zoning_layer = find_zoning_layer(canvas_layers, exclude_layer=object_layer)
        context = {
            "object_layer": object_layer.name() if object_layer else None,
            "zoning_layer": zoning_layer.name() if zoning_layer else None,
            "zoning_analysis_available": bool(object_layer and zoning_layer),
            "zoning_buffer_m": 500 if object_layer and zoning_layer else None,
            "object_detection": "selected feature > active layer > semantic name > single polygon layer",
            "zoning_detection": "name + attribute fields + polygon coverage evidence",
        }

        return {
            "schema_version": "1.1",
            "project": self.controller.project_info(),
            "active_layer_count": len(active),
            "active_layers": active,
            "context": context,
            "instructions_for_ai": [
                "Use only evidence present in this analysis.",
                "Do not infer a raster semantic class as certain from filename alone.",
                "For zoning, use the spatial analysis with a 500 m context when requested.",
                "Do not rename source layers; legend names are presentation labels only.",
                "If zoning confidence is insufficient, request or use explicit layer selection rather than guessing.",
            ],
        }
