"""Build a structured, AI-ready description of the active QGIS project."""

from .layer_analyzer import analyze_layer
from .legend_naming import classify_layer, is_legend_candidate, title_from_name
from .zoning import find_object_layer, find_zoning_layer


class ProjectAnalyzer:
    def __init__(self, controller):
        self.controller = controller

    def analyze(self):
        canvas_layers = list(self.controller.iface.mapCanvas().layers())
        all_layers = list(self.controller.project_info_layers())

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
            })
            active.append(item)

        object_layer = find_object_layer(canvas_layers)
        zoning_layer = find_zoning_layer(canvas_layers)
        context = {
            "object_layer": object_layer.name() if object_layer else None,
            "zoning_layer": zoning_layer.name() if zoning_layer else None,
            "zoning_analysis_available": bool(object_layer and zoning_layer),
            "zoning_buffer_m": 500 if object_layer and zoning_layer else None,
        }

        return {
            "schema_version": "1.0",
            "project": self.controller.project_info(),
            "active_layer_count": len(active),
            "active_layers": active,
            "context": context,
            "instructions_for_ai": [
                "Use only evidence present in this analysis.",
                "Do not infer a raster's semantic class as certain from filename alone.",
                "For zoning, use the spatial analysis with a 500 m context when requested.",
                "Do not rename source layers; legend names are presentation labels only.",
            ],
        }
