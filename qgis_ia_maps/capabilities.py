"""Capability discovery for QGIS-IA-MAPS.

This module exposes what the current QGIS installation can actually do.
It intentionally discovers capabilities from the local QGIS Processing
registry instead of hard-coding an imaginary global feature list.
"""

from qgis.core import QgsApplication


class CapabilityRegistry:
    """Read-only discovery over the current QGIS installation."""

    STATIC_GROUPS = {
        "project": [
            "project.info",
            "project.layers",
            "project.save",
            "project.context",
        ],
        "processing": [
            "processing.providers",
            "processing.algorithms",
            "processing.describe",
            "processing.run",
        ],
        "cartography": [
            "map.create_layout",
            "map.add_title",
            "map.add_legend",
            "map.add_scale",
            "map.export",
        ],
    }

    def providers(self):
        registry = QgsApplication.processingRegistry()
        output = []
        for provider in registry.providers():
            output.append({
                "id": provider.id(),
                "name": provider.name(),
                "active": bool(provider.isActive()),
                "algorithm_count": len(provider.algorithms()),
            })
        return sorted(output, key=lambda item: item["id"])

    def algorithms(self, provider_id=None, search=None, limit=1000):
        registry = QgsApplication.processingRegistry()
        search_text = (search or "").strip().lower()
        output = []
        for algorithm in registry.algorithms():
            alg_id = algorithm.id()
            provider = algorithm.provider()
            current_provider_id = provider.id() if provider else alg_id.split(":", 1)[0]
            if provider_id and current_provider_id != provider_id:
                continue
            display = algorithm.displayName()
            group = algorithm.group()
            if search_text and search_text not in alg_id.lower() and search_text not in display.lower() and search_text not in group.lower():
                continue
            output.append({
                "id": alg_id,
                "name": display,
                "group": group,
                "provider": current_provider_id,
                "can_cancel": bool(algorithm.flags() & algorithm.FlagCanCancel),
            })
            if len(output) >= int(limit):
                break
        return output

    def describe(self, algorithm_id):
        algorithm = QgsApplication.processingRegistry().algorithmById(str(algorithm_id))
        if algorithm is None:
            raise ValueError(f"Algoritmo Processing não encontrado: {algorithm_id}")

        parameters = []
        for parameter in algorithm.parameterDefinitions():
            parameters.append({
                "name": parameter.name(),
                "description": parameter.description(),
                "type": parameter.type(),
                "optional": bool(parameter.flags() & parameter.FlagOptional),
                "default": parameter.defaultValue(),
            })

        outputs = []
        for output in algorithm.outputDefinitions():
            outputs.append({
                "name": output.name(),
                "description": output.description(),
                "type": output.type(),
            })

        provider = algorithm.provider()
        return {
            "id": algorithm.id(),
            "name": algorithm.displayName(),
            "group": algorithm.group(),
            "provider": provider.id() if provider else None,
            "parameters": parameters,
            "outputs": outputs,
            "help": algorithm.shortHelpString() or "",
        }

    def snapshot(self):
        return {
            "static_groups": self.STATIC_GROUPS,
            "providers": self.providers(),
            "processing_algorithm_count": len(QgsApplication.processingRegistry().algorithms()),
        }
