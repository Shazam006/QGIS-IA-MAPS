"""Spatial zoning analysis around the map's object area.

The analysis is deterministic and uses the actual zoning layer attributes. It
finds the object area, builds a metric 500 m buffer, intersects that buffer
with zoning polygons, extracts the zoning name from likely attributes, and
selects only the relevant zoning features. The original layer names and
geometries are not modified.
"""

import math
import re

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsProject,
    QgsWkbTypes,
)


AREA_NAME_HINTS = (
    "area estudo",
    "area objeto",
    "area de estudo",
    "imovel",
    "propriedade",
    "terreno",
    "poligono estudo",
)

ZONE_NAME_FIELDS = (
    "nm_zone",
    "nome_zone",
    "nome_zona",
    "zona",
    "zoneamento",
    "classe",
    "categoria",
    "descricao",
    "descrição",
    "nm_zona",
    "ds_zone",
)


def _norm(value):
    text = str(value or "").strip().lower()
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _utm_crs_for_geometry(geometry, source_crs):
    """Choose a metric SIRGAS 2000 UTM CRS from the geometry centroid."""
    project = QgsProject.instance()
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    centroid = geometry.centroid()
    if source_crs != wgs84:
        centroid.transform(QgsCoordinateTransform(source_crs, wgs84, project))
    lon = centroid.asPoint().x()
    lat = centroid.asPoint().y()
    zone = int(math.floor((lon + 180.0) / 6.0) + 1)

    # SIRGAS 2000 / UTM south: EPSG 31978..31985 for zones 18..25.
    # SIRGAS 2000 / UTM north uses a different EPSG series; Brazil's
    # continental applications covered by this plugin are normally south.
    if lat < 0:
        if not 18 <= zone <= 25:
            raise ValueError(f"Zona UTM {zone}S fora da faixa SIRGAS 2000 suportada (18S-25S).")
        return QgsCoordinateReferenceSystem(f"EPSG:{31960 + zone}"), zone

    # North hemisphere: use WGS84 UTM only as a metric fallback because the
    # current target is Brazilian south-hemisphere municipal mapping.
    if not 18 <= zone <= 25:
        raise ValueError(f"Zona UTM {zone}N fora da faixa suportada.")
    return QgsCoordinateReferenceSystem(f"EPSG:{32600 + zone}"), zone


def _transform_geometry(geometry, source_crs, target_crs):
    project = QgsProject.instance()
    result = geometry.clone()
    if source_crs != target_crs:
        result.transform(QgsCoordinateTransform(source_crs, target_crs, project))
    return result


def find_object_layer(layers):
    """Prefer a selected polygon layer, then semantic area-name matches."""
    polygon_layers = [
        layer for layer in layers
        if layer.type() == 0 and layer.geometryType() == QgsWkbTypes.PolygonGeometry
    ]
    for layer in polygon_layers:
        if layer.selectedFeatureCount() > 0:
            return layer
    for layer in polygon_layers:
        name = _norm(layer.name())
        if any(hint in name for hint in AREA_NAME_HINTS):
            return layer
    return polygon_layers[0] if len(polygon_layers) == 1 else None


def find_zoning_layer(layers):
    """Identify the most likely active polygon zoning layer."""
    candidates = []
    for layer in layers:
        name = _norm(layer.name())
        if layer.type() != 0 or layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            continue
        score = 0
        if "zoneamento" in name or "macrozoneamento" in name:
            score += 5
        elif "zona" in name or "zone" in name or "macrozone" in name:
            score += 3
        fields = {_norm(field.name()) for field in layer.fields()}
        if any(_norm(field) in fields for field in ZONE_NAME_FIELDS):
            score += 4
        if score:
            candidates.append((score, layer))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def zoning_name(feature, layer):
    """Return the most plausible zoning-name attribute and its field."""
    fields = {field.name(): _norm(field.name()) for field in layer.fields()}
    for candidate in ZONE_NAME_FIELDS:
        for original, normalized in fields.items():
            if normalized == _norm(candidate):
                value = feature[original]
                if value not in (None, ""):
                    return str(value), original
    for field in layer.fields():
        normalized = _norm(field.name())
        if any(term in normalized for term in ("zone", "zona", "classe", "categoria", "descr")):
            value = feature[field.name()]
            if value not in (None, ""):
                return str(value), field.name()
    return (str(feature.attribute(0)) if layer.fields() else "Zona sem nome"), (layer.fields()[0].name() if layer.fields() else None)


def analyze_zoning(area_layer, zoning_layer, buffer_m=500, select=True):
    """Find zoning polygons inside or within buffer_m of the object area."""
    if area_layer is None or zoning_layer is None:
        raise ValueError("É necessário informar a camada da área objeto e a camada de zoneamento.")
    if area_layer.geometryType() != QgsWkbTypes.PolygonGeometry:
        raise ValueError("A área objeto precisa ser uma camada poligonal.")
    if zoning_layer.geometryType() != QgsWkbTypes.PolygonGeometry:
        raise ValueError("A camada de zoneamento precisa ser poligonal.")
    if buffer_m < 0:
        raise ValueError("buffer_m não pode ser negativo.")
    if not area_layer.crs().isValid() or not zoning_layer.crs().isValid():
        raise ValueError("Área objeto e zoneamento precisam possuir SRC válido.")

    area_features = list(area_layer.selectedFeatures()) or list(area_layer.getFeatures())
    if not area_features:
        raise ValueError("A camada da área objeto não possui feições.")

    area_geom = None
    for feature in area_features:
        geom = feature.geometry()
        if geom and not geom.isEmpty():
            area_geom = geom.clone() if area_geom is None else area_geom.combine(geom)
    if area_geom is None or area_geom.isEmpty():
        raise ValueError("Não foi possível obter a geometria da área objeto.")

    metric_crs, utm_zone = _utm_crs_for_geometry(area_geom, area_layer.crs())
    area_metric = _transform_geometry(area_geom, area_layer.crs(), metric_crs)
    search_geom = area_metric.buffer(float(buffer_m), 12)
    search_in_zoning = _transform_geometry(search_geom, metric_crs, zoning_layer.crs())

    request = QgsFeatureRequest().setFilterRect(search_in_zoning.boundingBox())
    candidates = []
    for feature in zoning_layer.getFeatures(request):
        geom = feature.geometry()
        if geom and not geom.isEmpty() and geom.intersects(search_in_zoning):
            candidates.append(feature)

    results = []
    selected_ids = []
    for feature in candidates:
        geom_metric = _transform_geometry(feature.geometry(), zoning_layer.crs(), metric_crs)
        distance = area_metric.distance(geom_metric)
        inside_object = bool(area_metric.intersects(geom_metric))
        name, field = zoning_name(feature, zoning_layer)
        results.append({
            "feature_id": feature.id(),
            "zoning_name": name,
            "name_field": field,
            "inside_object": inside_object,
            "distance_m": round(float(max(0.0, distance)), 2),
        })
        selected_ids.append(feature.id())

    results.sort(key=lambda item: (not item["inside_object"], item["distance_m"], item["zoning_name"]))
    if select:
        zoning_layer.removeSelection()
        zoning_layer.selectByIds(selected_ids)

    return {
        "success": True,
        "buffer_m": float(buffer_m),
        "utm_zone": utm_zone,
        "metric_crs": metric_crs.authid(),
        "area_layer": area_layer.name(),
        "zoning_layer": zoning_layer.name(),
        "selected_feature_ids": selected_ids,
        "zoning": results,
    }
