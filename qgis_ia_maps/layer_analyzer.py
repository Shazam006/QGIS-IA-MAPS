"""Deterministic first-pass analysis for active QGIS layers.

Raster analysis is intentionally conservative: metadata and sampled pixel
statistics can identify likely roles (imagery, elevation, index/classification)
but must not be presented as definitive semantic interpretation. A future AI
stage can use this structured evidence for deeper interpretation.
"""

import math
import re

from qgis.core import QgsMapLayer, QgsRasterBandStats, QgsRasterLayer, QgsWkbTypes


def _norm(value):
    text = str(value or "").strip().lower()
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _safe_stats(layer, band):
    try:
        provider = layer.dataProvider()
        stats = provider.bandStatistics(
            band,
            QgsRasterBandStats.All,
            layer.extent(),
            100000,
        )
        return {
            "minimum": stats.minimumValue,
            "maximum": stats.maximumValue,
            "mean": stats.mean,
            "stddev": stats.stdDev,
            "range": stats.maximumValue - stats.minimumValue,
        }
    except Exception as exc:
        return {"error": str(exc)}


def analyze_raster(layer):
    if not isinstance(layer, QgsRasterLayer):
        raise ValueError("A camada informada não é raster.")

    provider = layer.dataProvider()
    bands = []
    for band in range(1, layer.bandCount() + 1):
        stats = _safe_stats(layer, band)
        bands.append({"band": band, "stats": stats})

    name = _norm(layer.name())
    source = _norm(layer.source())
    provider_name = _norm(provider.name()) if provider else ""
    text = " ".join((name, source, provider_name))

    hints = []
    if any(term in text for term in ("ndvi", "vegetacao", "vegetação", "normalized difference vegetation")):
        hints.append("vegetação/índice espectral")
    if any(term in text for term in ("ndwi", "agua", "água", "water")):
        hints.append("água/índice espectral")
    if any(term in text for term in ("ndbi", "construido", "construído", "built")):
        hints.append("área construída/índice espectral")
    if any(term in text for term in ("ndmi", "umidade", "moisture")):
        hints.append("umidade/índice espectral")
    if any(term in text for term in ("dem", "dtm", "dsm", "elevacao", "elevação", "altitude", "declividade", "srtm", "alos")):
        hints.append("modelo de elevação/topografia")
    if any(term in text for term in ("sentinel", "landsat", "cbers", "planet", "ortofoto", "ortomosaico", "imagem", "satellite", "satélite")):
        hints.append("imagem/observação da Terra")
    if any(term in text for term in ("class", "classificacao", "classificação", "lulc", "uso solo", "uso do solo")):
        hints.append("classificação/uso e cobertura")

    if layer.bandCount() == 1:
        interpretation = "raster de banda única"
    elif layer.bandCount() >= 3:
        interpretation = "raster multibanda"
    else:
        interpretation = "raster"

    if hints:
        interpretation += "; possíveis usos: " + ", ".join(dict.fromkeys(hints))

    return {
        "name": layer.name(),
        "type": "raster",
        "crs": layer.crs().authid() if layer.crs().isValid() else None,
        "width": layer.width(),
        "height": layer.height(),
        "band_count": layer.bandCount(),
        "provider": provider.name() if provider else None,
        "extent": layer.extent().toString(),
        "pixel_size": {
            "x": layer.rasterUnitsPerPixelX(),
            "y": layer.rasterUnitsPerPixelY(),
        },
        "bands": bands,
        "interpretation": interpretation,
        "hints": list(dict.fromkeys(hints)),
    }


def analyze_vector(layer):
    fields = [field.name() for field in layer.fields()]
    geometry_name = QgsWkbTypes.displayString(layer.wkbType())
    return {
        "name": layer.name(),
        "type": "vector",
        "geometry": geometry_name,
        "crs": layer.crs().authid() if layer.crs().isValid() else None,
        "feature_count": layer.featureCount(),
        "fields": fields,
    }


def analyze_layer(layer):
    if layer.type() == QgsMapLayer.RasterLayer:
        return analyze_raster(layer)
    if layer.type() == QgsMapLayer.VectorLayer:
        return analyze_vector(layer)
    return {"name": layer.name(), "type": "other"}
