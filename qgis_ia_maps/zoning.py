"""Spatial zoning analysis around the map's object area."""

import math
import re

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeatureRequest, QgsProject, QgsWkbTypes

AREA_NAME_HINTS = ("area estudo", "area objeto", "area de estudo", "imovel", "propriedade", "terreno", "poligono estudo", "lote", "gleba")
ZONE_NAME_FIELDS = ("nm_zone", "nome_zone", "nome_zona", "zona", "zoneamento", "classe", "categoria", "descricao", "descrição", "nm_zona", "ds_zone", "cod_zone", "codigo_zona", "codigo_zone")
ZONE_NAME_HINTS = ("zoneamento", "macrozoneamento", "zone", "zona", "zoneamento municipal", "macrozone")


def _norm(value):
    text = str(value or "").strip().lower()
    text = re.sub(r"[_-]+", " ", text)
    return re.sub(r"\s+", " ", text)


def _utm_crs_for_geometry(geometry, source_crs):
    project = QgsProject.instance()
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    centroid = geometry.centroid()
    if source_crs != wgs84:
        centroid.transform(QgsCoordinateTransform(source_crs, wgs84, project))
    lon, lat = centroid.asPoint().x(), centroid.asPoint().y()
    zone = int(math.floor((lon + 180.0) / 6.0) + 1)
    if lat < 0:
        if not 18 <= zone <= 25:
            raise ValueError(f"Zona UTM {zone}S fora da faixa SIRGAS 2000 suportada.")
        return QgsCoordinateReferenceSystem(f"EPSG:{31960 + zone}"), zone
    if not 18 <= zone <= 25:
        raise ValueError(f"Zona UTM {zone}N fora da faixa suportada.")
    return QgsCoordinateReferenceSystem(f"EPSG:{32600 + zone}"), zone


def _transform_geometry(geometry, source_crs, target_crs):
    result = geometry.clone()
    if source_crs != target_crs:
        result.transform(QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance()))
    return result


def _polygon_layers(layers):
    return [layer for layer in layers if layer.type() == 0 and layer.geometryType() == QgsWkbTypes.PolygonGeometry]


def find_object_layer(layers, active_layer=None):
    """Find the object area using selection, active layer, semantic names and simple geometry heuristics."""
    polygons = _polygon_layers(layers)
    if not polygons:
        return None
    # Strongest signal: selected polygon feature.
    selected = [layer for layer in polygons if layer.selectedFeatureCount() > 0]
    if selected:
        return selected[0]
    # Next: the layer currently active in the QGIS Layers panel.
    if active_layer in polygons:
        return active_layer
    # Then semantic layer names.
    for layer in polygons:
        name = _norm(layer.name())
        if any(hint in name for hint in AREA_NAME_HINTS):
            return layer
    # A single polygon layer is unambiguous.
    if len(polygons) == 1:
        return polygons[0]
    return None


def _field_score(layer):
    fields = {_norm(field.name()) for field in layer.fields()}
    exact = sum(1 for field in ZONE_NAME_FIELDS if _norm(field) in fields)
    semantic = sum(1 for field in fields if any(k in field for k in ("zone", "zona", "classe", "categoria", "descr")))
    return exact * 6 + semantic * 2


def find_zoning_layer(layers, exclude_layer=None):
    """Identify the most likely polygon zoning layer, including unnamed municipal datasets."""
    candidates = []
    for layer in _polygon_layers(layers):
        if exclude_layer is not None and layer.id() == exclude_layer.id():
            continue
        name = _norm(layer.name())
        score = _field_score(layer)
        if any(term in name for term in ZONE_NAME_HINTS):
            score += 10
        # A zoning dataset is commonly a multi-feature polygon coverage.
        count = layer.featureCount()
        if count > 1:
            score += min(6, math.log10(max(count, 1)) * 2)
        # Single-feature municipal boundary/property layers are weak candidates.
        if count == 1:
            score -= 4
        if score > 0:
            candidates.append((score, count, layer))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def zoning_name(feature, layer):
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
    # Last resort: find a populated string attribute with repeated categorical values.
    for field in layer.fields():
        try:
            value = feature[field.name()]
            if isinstance(value, str) and value.strip():
                return value.strip(), field.name()
        except Exception:
            pass
    return ("Zona sem nome", None)


def analyze_zoning(area_layer, zoning_layer, buffer_m=500, select=True):
    if area_layer is None or zoning_layer is None:
        raise ValueError("É necessário identificar a área objeto e a camada de zoneamento.")
    if area_layer.geometryType() != QgsWkbTypes.PolygonGeometry or zoning_layer.geometryType() != QgsWkbTypes.PolygonGeometry:
        raise ValueError("A área objeto e o zoneamento precisam ser camadas poligonais.")
    if not area_layer.crs().isValid() or not zoning_layer.crs().isValid():
        raise ValueError("Área objeto e zoneamento precisam possuir SRC válido.")
    area_features = list(area_layer.selectedFeatures()) or list(area_layer.getFeatures())
    if not area_features:
        raise ValueError(f"A camada '{area_layer.name()}' não possui feições para usar como área objeto.")
    area_geom = None
    for feature in area_features:
        geom = feature.geometry()
        if geom and not geom.isEmpty():
            area_geom = geom.clone() if area_geom is None else area_geom.combine(geom)
    if area_geom is None or area_geom.isEmpty():
        raise ValueError("Não foi possível obter uma geometria válida da área objeto.")

    metric_crs, utm_zone = _utm_crs_for_geometry(area_geom, area_layer.crs())
    area_metric = _transform_geometry(area_geom, area_layer.crs(), metric_crs)
    search_geom = area_metric.buffer(float(buffer_m), 16)
    search_in_zoning = _transform_geometry(search_geom, metric_crs, zoning_layer.crs())
    request = QgsFeatureRequest().setFilterRect(search_in_zoning.boundingBox())

    results, selected_ids = [], []
    for feature in zoning_layer.getFeatures(request):
        geom = feature.geometry()
        if not geom or geom.isEmpty() or not geom.intersects(search_in_zoning):
            continue
        geom_metric = _transform_geometry(geom, zoning_layer.crs(), metric_crs)
        inside = bool(area_metric.intersects(geom_metric))
        distance = 0.0 if inside else area_metric.distance(geom_metric)
        name, field = zoning_name(feature, zoning_layer)
        results.append({"feature_id": feature.id(), "zoning_name": name, "name_field": field, "inside_object": inside, "distance_m": round(float(max(0.0, distance)), 2)})
        selected_ids.append(feature.id())
    results.sort(key=lambda item: (not item["inside_object"], item["distance_m"], item["zoning_name"]))
    if select:
        zoning_layer.removeSelection()
        zoning_layer.selectByIds(selected_ids)
    return {"success": True, "buffer_m": float(buffer_m), "utm_zone": utm_zone, "metric_crs": metric_crs.authid(), "area_layer": area_layer.name(), "zoning_layer": zoning_layer.name(), "selected_feature_ids": selected_ids, "zoning": results}
