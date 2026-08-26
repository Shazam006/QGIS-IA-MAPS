import re


# Conservative, deterministic names first. The original layer name is never
# changed; these labels are intended for the legend only.
NAME_RULES = [
    (r"\barea[_ -]?estudo\b", "Área de Estudo"),
    (r"\barea[_ -]?urbana\b", "Área Urbana"),
    (r"\barea[_ -]?rural\b", "Área Rural"),
    (r"\blimite[_ -]?municip(al|io)\b|\bmunicipio\b", "Limite Municipal"),
    (r"\blimite[_ -]?imovel\b|\bimovel\b|\bpropriedade\b", "Limite do Imóvel"),
    (r"\bhidrograf(ia|ica|ico)\b|\brio(s)?\b|\bc[óo]rrego(s)?\b|\bnascente(s)?\b", "Hidrografia"),
    (r"\bcurso[_ -]?hidrico\b", "Curso Hídrico"),
    (r"\brodovia(s)?\b|\bvia(s)?\b|\bestrada(s)?\b|\brua(s)?\b", "Vias"),
    (r"\bferrovia(s)?\b|\blinha[_ -]?ferrea\b", "Ferrovias"),
    (r"\bvegetacao\b|\bvegetal\b|\bvegetacao[_ -]?nativa\b", "Vegetação"),
    (r"\bapp\b|\barea[_ -]?preservacao[_ -]?permanente\b", "Área de Preservação Permanente"),
    (r"\breserva[_ -]?legal\b|\brl\b", "Reserva Legal"),
    (r"\buso[_ -]?e?[_ -]?ocupacao[_ -]?do?[_ -]?solo\b|\buso[_ -]?solo\b", "Uso e Cobertura da Terra"),
    (r"\buso[_ -]?cobertura\b|\bcobertura[_ -]?terra\b", "Uso e Cobertura da Terra"),
    (r"\bcurva(s)?[_ -]?nivel\b|\bcontorno(s)?\b", "Curvas de Nível"),
    (r"\bdeclividade\b|\bslope\b", "Declividade"),
    (r"\bhipsometria\b|\belevacao\b|\baltimetria\b", "Hipsometria"),
    (r"\bmunicipios\b", "Municípios"),
    (r"\bsetor(es)?\b|\bbairro(s)?\b", "Setores / Bairros"),
    (r"\bzoneamento\b|\bzoneamento[_ -]?municipal\b|\buso[_ -]?do[_ -]?solo\b", "Zoneamento"),
    (r"\bmacrozoneamento\b|\bmacrozona(s)?\b", "Macrozoneamento"),
    (r"\bcar\b|\bcadastro[_ -]?ambiental[_ -]?rural\b", "Cadastro Ambiental Rural"),
    (r"\bnascentes?\b", "Nascentes"),
    (r"\bapp\b", "Área de Preservação Permanente"),
    (r"\bgoogle[_ -]?satellite\b|\bsatellite\b|\bsat[eé]lite\b", "Imagem de Satélite"),
    (r"\bopenstreetmap\b|\bosm\b", "OpenStreetMap"),
]

EXCLUDED_RASTER_NAMES = re.compile(
    r"google|satellite|sat[eé]lite|osm|openstreetmap|basemap|fundo|imagem[_ -]?aerea",
    re.IGNORECASE,
)


def normalize(value):
    text = (value or "").strip().lower()
    text = re.sub(r"[./\\]+", " ", text)
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def title_from_name(name):
    normalized = normalize(name)
    for pattern, label in NAME_RULES:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return label
    # Safe fallback: humanize the technical name without pretending to know
    # its semantic meaning.
    cleaned = re.sub(r"[_-]+", " ", (name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return "Camada"
    return cleaned[:1].upper() + cleaned[1:]


def classify_layer(layer):
    """Return a deterministic semantic hint from name, geometry and fields."""
    name = normalize(layer.name())
    geometry = ""
    try:
        geometry = str(layer.geometryType()).lower()
    except Exception:
        pass
    fields = []
    try:
        fields = [normalize(f.name()) for f in layer.fields()]
    except Exception:
        pass
    joined = " ".join([name, geometry, " ".join(fields)])

    if re.search(r"\b(app|area preservacao permanente)\b", joined):
        category = "APP"
    elif re.search(r"\b(hidro|hidrograf|rio|corrego|nascente|curso hidrico)\b", joined):
        category = "Hidrografia"
    elif re.search(r"\b(rodovia|estrada|rua|via|logradouro)\b", joined):
        category = "Vias"
    elif re.search(r"\b(veget|flora|fitofision)\b", joined):
        category = "Vegetação"
    elif re.search(r"\b(uso|cobertura|ocupacao|classe)\b", joined):
        category = "Uso e Cobertura da Terra"
    elif re.search(r"\b(mun|municip|codigo_mun|cd_mun|nm_mun)\b", joined):
        category = "Municípios"
    elif re.search(r"\b(zone|zoning|zoneamento|macrozone)\b", joined):
        category = "Zoneamento"
    else:
        category = ""

    return {"category": category, "geometry": geometry, "fields": fields}


def is_legend_candidate(layer):
    """Exclude common raster basemaps from the automatic legend."""
    try:
        layer_type = layer.type()
        # QgsMapLayer.RasterLayer == 1 in QGIS 3.x; avoid importing enums here.
        if int(layer_type) == 1 and EXCLUDED_RASTER_NAMES.search(layer.name() or ""):
            return False
    except Exception:
        pass
    return True
