def classFactory(iface):
    from .qgis_ia_maps import QGISIAMaps
    return QGISIAMaps(iface)
