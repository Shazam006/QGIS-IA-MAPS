"""Validated execution of QGIS Processing algorithms.

This is the generic execution backbone for the agentic QGIS assistant. It does
not execute arbitrary Python. It only runs algorithms registered in the current
QGIS Processing registry after validating the requested algorithm and basic
parameter structure.
"""

from pathlib import Path

import processing
from qgis.core import QgsApplication, QgsProcessingContext, QgsProcessingFeedback, QgsProject


class ProcessingExecutor:
    def __init__(self, iface):
        self.iface = iface

    @staticmethod
    def _algorithm(algorithm_id):
        algorithm = QgsApplication.processingRegistry().algorithmById(str(algorithm_id))
        if algorithm is None:
            raise ValueError(f"Algoritmo Processing não encontrado: {algorithm_id}")
        return algorithm

    @staticmethod
    def _parameter_names(algorithm):
        return {parameter.name() for parameter in algorithm.parameterDefinitions()}

    def validate(self, algorithm_id, parameters):
        if not isinstance(parameters, dict):
            raise ValueError("Os parâmetros do algoritmo precisam ser um objeto/dicionário.")

        algorithm = self._algorithm(algorithm_id)
        known = self._parameter_names(algorithm)
        unknown = sorted(set(parameters) - known)
        if unknown:
            raise ValueError(
                "Parâmetros não reconhecidos para "
                f"{algorithm_id}: {', '.join(unknown)}"
            )

        missing = []
        for definition in algorithm.parameterDefinitions():
            optional = bool(definition.flags() & definition.FlagOptional)
            if optional:
                continue
            if definition.defaultValue() not in (None, ""):
                continue
            if definition.name() not in parameters:
                missing.append(definition.name())
        return {
            "algorithm_id": algorithm.id(),
            "algorithm_name": algorithm.displayName(),
            "missing_required": missing,
            "valid": not missing,
        }

    @staticmethod
    def _normalise_result(value):
        if hasattr(value, "id") and callable(value.id):
            return {"layer_id": value.id(), "name": value.name()}
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {k: ProcessingExecutor._normalise_result(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [ProcessingExecutor._normalise_result(v) for v in value]
        return value

    def run(self, algorithm_id, parameters, add_outputs_to_project=True):
        validation = self.validate(algorithm_id, parameters)
        if not validation["valid"]:
            raise ValueError(
                "Parâmetros obrigatórios ausentes: "
                + ", ".join(validation["missing_required"])
            )

        context = QgsProcessingContext()
        context.setProject(QgsProject.instance())
        feedback = QgsProcessingFeedback()

        result = processing.run(
            str(algorithm_id),
            dict(parameters),
            context=context,
            feedback=feedback,
            is_child_algorithm=False,
        )

        added = []
        if add_outputs_to_project:
            details = context.layersToLoadOnCompletion()
            for layer_id, detail in details.items():
                try:
                    layer = detail.outputLayer
                    if layer is not None and QgsProject.instance().mapLayer(layer.id()) is None:
                        QgsProject.instance().addMapLayer(layer)
                        added.append({"id": layer.id(), "name": layer.name()})
                except Exception:
                    continue

        return {
            "success": True,
            "algorithm": validation,
            "result": self._normalise_result(result),
            "added_layers": added,
        }
