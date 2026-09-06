from pathlib import Path
from qgis.PyQt.QtCore import QObject, Qt
from qgis.PyQt.QtWidgets import QAction, QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QTextEdit
from qgis.core import QgsProject, QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemScaleBar, QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes, QgsLayoutExporter, QgsLayerTreeGroup, QgsWkbTypes
from .legend_naming import classify_layer, is_legend_candidate, title_from_name
from .mcp_bridge import MCPBridge
from .zoning import analyze_zoning, find_object_layer, find_zoning_layer
from .project_analyzer import ProjectAnalyzer
from .template_manager import TemplateManager
from .ui import button, card, apply_style


class QGISIAMaps(QObject):
    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.action = None
        self.dock = None
        self.status = None
        self.summary = None
        self.log = None
        self.bridge = MCPBridge(self)
        self.analyzer = ProjectAnalyzer(self)
        self.template_manager = TemplateManager(iface, self)

    def initGui(self):
        self.action = QAction("QGIS-IA-MAPS", self.iface.mainWindow())
        self.action.triggered.connect(self.show_dock)
        self.iface.addPluginToMenu("&QGIS-IA-MAPS", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.bridge.stop()
        if self.action:
            self.iface.removePluginMenu("&QGIS-IA-MAPS", self.action)
            self.iface.removeToolBarIcon(self.action)
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

    def show_dock(self):
        if self.dock is None:
            self.dock = QDockWidget("QGIS-IA-MAPS", self.iface.mainWindow())
            self.dock.setObjectName("QGISIAMapsDock")
            self.dock.setMinimumWidth(370)
            self.dock.setMaximumWidth(540)
            self.dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
            root = QWidget()
            main = QVBoxLayout(root)
            main.setContentsMargins(12, 12, 12, 12)
            main.setSpacing(10)

            header = QHBoxLayout()
            brand = QVBoxLayout()
            title = QLabel("QGIS-IA-MAPS"); title.setObjectName("title")
            subtitle = QLabel("Automação cartográfica inteligente"); subtitle.setObjectName("subtitle")
            brand.addWidget(title); brand.addWidget(subtitle); header.addLayout(brand, 1)
            dot = QLabel("●"); dot.setObjectName("dot"); header.addWidget(dot, 0, Qt.AlignTop)
            main.addLayout(header)
            self.status = QLabel("Pronto para analisar o projeto"); self.status.setObjectName("status"); main.addWidget(self.status)

            tabs = QTabWidget()
            tabs.addTab(self._project_tab(), "Projeto")
            tabs.addTab(self._analysis_tab(), "Análise")
            tabs.addTab(self._maps_tab(), "Mapas")
            tabs.addTab(self._ia_tab(), "IA / MCP")
            main.addWidget(tabs, 1)

            log_card, log_layout = card("Registro", "Operações e diagnósticos")
            self.log = QTextEdit(); self.log.setObjectName("log"); self.log.setReadOnly(True); self.log.setMinimumHeight(120)
            log_layout.addWidget(self.log); main.addWidget(log_card)
            self.dock.setWidget(root)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
            apply_style(self.dock)
            self._refresh_summary()
        self.dock.show(); self.dock.raise_()

    def _project_tab(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(2, 8, 2, 2)
        c, box = card("Projeto atual", "Analise primeiro as camadas que estão visíveis no mapa.")
        self.summary = QLabel("0 camadas · 0 ativas"); self.summary.setObjectName("metric"); box.addWidget(self.summary)
        box.addWidget(button("Ler projeto atual", self.test_project, True))
        box.addWidget(button("Analisar todas as camadas", self.analyze_project))
        lay.addWidget(c)
        c2, b2 = card("Fluxo recomendado", "Evita decisões cartográficas baseadas apenas em nomes de arquivos.")
        for text in ("1. Deixe visíveis as camadas desejadas", "2. Selecione a área objeto quando necessário", "3. Execute a análise", "4. Gere o mapa pelo template padrão"):
            x = QLabel(text); x.setWordWrap(True); b2.addWidget(x)
        lay.addWidget(c2); lay.addStretch(); return page

    def _analysis_tab(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(2, 8, 2, 2)
        c, box = card("Análise espacial", "Interpretação técnica antes da geração cartográfica.")
        box.addWidget(button("Analisar projeto", self.analyze_project, True))
        box.addWidget(button("Zoneamento + 500 m", self.analyze_zoning_500m))
        box.addWidget(button("Listar candidatas", self.list_layer_candidates))
        lay.addWidget(c)
        c2, b2 = card("O que é verificado")
        for text in ("Vetores: geometria, SRC, feições, campos e classificação", "Rasters: bandas, resolução, extensão e estatísticas", "Zoneamento: área objeto, zonas relevantes e 500 m", "Legenda: nomes cartográficos sem alterar a fonte"):
            x = QLabel("• " + text); x.setWordWrap(True); b2.addWidget(x)
        lay.addWidget(c2); lay.addStretch(); return page

    def _maps_tab(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(2, 8, 2, 2)
        c, box = card("Geração de mapas", "O template QPT preserva seu padrão visual.")
        box.addWidget(button("Criar A4 pelo template", self.create_template_map, True))
        box.addWidget(button("Criar A4 simples", self.create_a4_map))
        box.addWidget(button("Exportar layout atual", self.export_current_layout))
        lay.addWidget(c)
        c2, b2 = card("Regras cartográficas")
        for text in ("Legenda usa nomes cartográficos", "Até 4 polígonos: símbolos 8 × 4 mm", "Mais de 4 polígonos: símbolos 4 × 2 mm", "Rasters de fundo podem ficar fora da legenda"):
            x = QLabel("• " + text); x.setWordWrap(True); b2.addWidget(x)
        lay.addWidget(c2); lay.addStretch(); return page

    def _ia_tab(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(2, 8, 2, 2)
        c, box = card("Ponte local", "Canal preparado para conectar um agente ao QGIS com comandos controlados.")
        box.addWidget(button("Iniciar / parar ponte", self.toggle_bridge, True))
        x = QLabel("127.0.0.1:9877"); x.setObjectName("muted"); box.addWidget(x); lay.addWidget(c)
        c2, b2 = card("Arquitetura")
        for text in ("Análise → decisão estruturada → validação → QGIS", "Operações espaciais permanecem no PyQGIS", "O GPT não deve executar código arbitrário no QGIS"):
            y = QLabel("• " + text); y.setWordWrap(True); b2.addWidget(y)
        lay.addWidget(c2); lay.addStretch(); return page

    def _refresh_summary(self):
        if self.summary:
            p = QgsProject.instance(); self.summary.setText(f"{len(p.mapLayers())} camadas · {len(self._visible_canvas_layers())} ativas")

    def log_message(self, msg):
        if self.log: self.log.append(str(msg))

    def toggle_bridge(self):
        try:
            if self.bridge.running: self.bridge.stop(); self.status.setText("Ponte local parada")
            else: self.bridge.start(); self.status.setText(f"Ponte local ativa em {self.bridge.host}:{self.bridge.port}")
            self.log_message("Ponte local: " + ("ATIVA" if self.bridge.running else "PARADA"))
        except Exception as exc: self.status.setText("Erro ao iniciar a ponte"); self.log_message("ERRO: " + str(exc))

    def project_info_layers(self): return list(QgsProject.instance().mapLayers().values())
    def project_info(self):
        p = QgsProject.instance(); return {"path": p.fileName(), "title": p.title(), "layer_count": len(p.mapLayers()), "crs": p.crs().authid()}
    def _visible_canvas_layers(self): return list(self.iface.mapCanvas().layers())

    def list_layers(self):
        root = QgsProject.instance().layerTreeRoot(); active = {l.id() for l in self._visible_canvas_layers()}; out = []
        for l in QgsProject.instance().mapLayers().values():
            n = root.findLayer(l.id()); out.append({"id": l.id(), "name": l.name(), "type": l.type(), "source": l.source(), "visible": bool(n and n.isVisible()), "active_in_canvas": l.id() in active, "crs": l.crs().authid() if l.crs().isValid() else None, "legend_name": title_from_name(l.name()), "classification": classify_layer(l)})
        return out

    def test_project(self):
        try:
            i = self.project_info(); self.status.setText("Projeto lido com sucesso"); self._refresh_summary(); self.log_message("Projeto: " + (i["path"] or "(não salvo)")); self.log_message("Camadas: " + str(i["layer_count"]))
            for x in self.list_layers(): self.log_message(f"- {x['name']} [{'ATIVA' if x['active_in_canvas'] else 'oculta'}] ({'raster' if x['type']==1 else 'vetor'})")
        except Exception as exc: self.status.setText("Erro ao ler projeto"); self.log_message("ERRO: " + str(exc))

    def analyze_project(self):
        try:
            r = self.analyzer.analyze(); self.status.setText("Projeto analisado"); self._refresh_summary(); self.log_message(f"Análise: {r['active_layer_count']} camadas ativas.")
            for x in r["active_layers"]: self.log_message(f"- {x['name']} → {x['legend_name']} | {x['type']} | {x.get('interpretation', x.get('geometry', ''))}")
            c = r["context"]; self.log_message("Área objeto: " + (c["object_layer"] or "não identificada")); self.log_message("Zoneamento: " + (c["zoning_layer"] or "não identificado")); return r
        except Exception as exc: self.status.setText("Erro na análise"); self.log_message("ERRO: " + str(exc)); return None

    def list_layer_candidates(self):
        self.log_message("Camadas poligonais candidatas:")
        for l in self._visible_canvas_layers():
            if l.type() == 0 and l.geometryType() == QgsWkbTypes.PolygonGeometry: self.log_message(f"- {l.name()} | {l.featureCount()} feições | campos: {', '.join(f.name() for f in l.fields())}")
        self.status.setText("Candidatas listadas")

    def analyze_zoning_500m(self):
        try:
            layers = self._visible_canvas_layers(); area = find_object_layer(layers, active_layer=self.iface.activeLayer()); z = find_zoning_layer(layers, exclude_layer=area)
            if not area: raise ValueError("Área objeto não identificada. Selecione uma feição poligonal da área objeto.")
            if not z: self.list_layer_candidates(); raise ValueError("Zoneamento não identificado automaticamente.")
            r = analyze_zoning(area, z, 500, True); self.status.setText("Zoneamento analisado"); self.log_message(f"Área: {r['area_layer']} | Zoneamento: {r['zoning_layer']} | raio: 500 m")
            for x in r["zoning"]: self.log_message(f"- {x['zoning_name']} [{'NA ÁREA' if x['inside_object'] else str(x['distance_m']) + ' m'}]")
            return r
        except Exception as exc: self.status.setText("Erro no zoneamento"); self.log_message("ERRO: " + str(exc)); return None

    def _legend_tree_for_active_layers(self):
        project = QgsProject.instance(); active = {l.id() for l in self._visible_canvas_layers()}; root = project.layerTreeRoot().clone()
        for node in list(root.findLayers()):
            l = node.layer(); keep = l is not None and l.id() in active and is_legend_candidate(l)
            if not keep:
                p = node.parent()
                if isinstance(p, QgsLayerTreeGroup): p.removeChildNode(node)
            else: node.setName(title_from_name(l.name())); node.setUseLayerName(False)
        root.removeChildrenGroupWithoutLayers(); return root

    def _polygon_layer_count(self): return sum(1 for l in self._visible_canvas_layers() if is_legend_candidate(l) and l.type() == 0 and l.geometryType() == QgsWkbTypes.PolygonGeometry)
    def _legend_symbol_size(self): n = self._polygon_layer_count(); return (8.0, 4.0, n) if n <= 4 else (4.0, 2.0, n)

    def create_a4_map(self):
        self.create_layout("Mapa IA", "A4", "landscape"); self.add_title("Mapa IA", "MAPA GERADO PELO QGIS-IA-MAPS"); self.add_legend("Mapa IA"); self.add_scale("Mapa IA"); self.status.setText("Mapa A4 criado"); self.log_message("Mapa A4 simples criado.")

    def create_layout(self, name="Mapa IA", page="A4", orientation="landscape"):
        if page.upper() != "A4": raise ValueError("Somente A4.")
        p = QgsProject.instance(); old = p.layoutManager().layoutByName(name)
        if old: p.layoutManager().removeLayout(old)
        w, h = (297, 210) if orientation.lower() == "landscape" else (210, 297)
        l = QgsPrintLayout(p); l.initializeDefaults(); l.setName(name); l.pageCollection().page(0).setPageSize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters)); p.layoutManager().addLayout(l)
        m = QgsLayoutItemMap(l); m.attemptMove(QgsLayoutPoint(10, 18, QgsUnitTypes.LayoutMillimeters)); m.attemptResize(QgsLayoutSize(w - 80, h - 48, QgsUnitTypes.LayoutMillimeters)); m.setFrameEnabled(True); layers = self._visible_canvas_layers()
        if layers: m.setLayers(layers); e = self.iface.mapCanvas().extent(); e.scale(1.05); m.setExtent(e)
        l.addLayoutItem(m); return {"name": name, "page": "A4", "orientation": orientation.lower()}

    def _layout(self, name):
        l = QgsProject.instance().layoutManager().layoutByName(name)
        if not l: raise ValueError("Layout não encontrado: " + name)
        return l

    def _first_map(self, l):
        maps = [x for x in l.items() if isinstance(x, QgsLayoutItemMap)]
        if not maps: raise ValueError("Layout sem mapa")
        return maps[0]

    def add_title(self, name, text, size=14, x=10, y=5):
        l = self._layout(name); i = QgsLayoutItemLabel(l); i.setText(str(text)); i.setFontPointSize(float(size)); i.adjustSizeToText(); i.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters)); l.addLayoutItem(i); return True

    def add_legend(self, name, title="Legenda", x=225, y=18):
        l = self._layout(name); g = QgsLayoutItemLegend(l); g.setTitle(str(title)); g.setLinkedMap(self._first_map(l)); g.setAutoUpdateModel(False); g.model().setRootGroup(self._legend_tree_for_active_layers()); w, h, n = self._legend_symbol_size(); g.setSymbolWidth(w); g.setSymbolHeight(h); g.refresh(); g.adjustBoxSize(); g.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters)); l.addLayoutItem(g); return {"success": True, "polygon_layer_count": n, "symbol_size_mm": {"width": w, "height": h}}

    def add_scale(self, name, x=10, y=185):
        l = self._layout(name); s = QgsLayoutItemScaleBar(l); s.setStyle("Single Box"); s.setUnits(QgsUnitTypes.DistanceMeters); s.setNumberOfSegments(4); s.setNumberOfSegmentsLeft(0); s.setLinkedMap(self._first_map(l)); s.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters)); l.addLayoutItem(s); return True

    def create_template_map(self):
        try:
            l = self.template_manager.load_template("Mapa IA"); self.template_manager.bind_active_layers(l); self.template_manager.update_legend(l); self.status.setText("Template QPT carregado"); self.log_message("Template QPT carregado com as camadas ativas.")
        except Exception as exc: self.status.setText("Erro no template QPT"); self.log_message("ERRO: " + str(exc))

    def export_current_layout(self):
        try:
            l = QgsProject.instance().layoutManager().layoutByName("Mapa IA")
            if not l: raise ValueError("Nenhum layout 'Mapa IA' foi criado.")
            path = Path(QgsProject.instance().fileName()).with_name("mapa_ia.pdf") if QgsProject.instance().fileName() else Path.home() / "mapa_ia.pdf"
            r = QgsLayoutExporter(l).exportToPdf(str(path), QgsLayoutExporter.PdfExportSettings())
            if r != QgsLayoutExporter.Success: raise RuntimeError("Falha ao exportar PDF.")
            self.status.setText("PDF exportado"); self.log_message("PDF: " + str(path)); return {"success": True, "path": str(path)}
        except Exception as exc: self.status.setText("Erro na exportação"); self.log_message("ERRO: " + str(exc)); return None

    def export_layout(self, name, path, format="pdf"):
        l = self._layout(name); o = Path(path).expanduser(); o.parent.mkdir(parents=True, exist_ok=True); e = QgsLayoutExporter(l); f = str(format).lower(); r = e.exportToPdf(str(o), QgsLayoutExporter.PdfExportSettings()) if f == "pdf" else e.exportToImage(str(o), QgsLayoutExporter.ImageExportSettings()) if f == "png" else None
        if r != QgsLayoutExporter.Success: raise RuntimeError("Falha na exportação")
        return {"success": True, "path": str(o)}

    def save_project(self, path=None):
        p = QgsProject.instance()
        if path: p.setFileName(str(Path(path).expanduser()))
        if not p.write(): raise RuntimeError("Falha ao salvar projeto")
        return {"success": True, "path": p.fileName()}
