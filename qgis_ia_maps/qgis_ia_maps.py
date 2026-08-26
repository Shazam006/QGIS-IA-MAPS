from pathlib import Path
from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtWidgets import QAction,QDockWidget,QWidget,QVBoxLayout,QLabel,QPushButton,QTextEdit
from qgis.core import QgsProject,QgsPrintLayout,QgsLayoutItemMap,QgsLayoutItemLabel,QgsLayoutItemLegend,QgsLayoutItemScaleBar,QgsLayoutPoint,QgsLayoutSize,QgsUnitTypes,QgsLayoutExporter,QgsLayerTree,QgsWkbTypes
from .legend_naming import classify_layer,is_legend_candidate,title_from_name
from .mcp_bridge import MCPBridge
from .zoning import analyze_zoning,find_object_layer,find_zoning_layer
from .project_analyzer import ProjectAnalyzer

class QGISIAMaps(QObject):
    def __init__(self,iface):
        super().__init__();self.iface=iface;self.action=None;self.dock=None;self.status=None;self.log=None;self.bridge=MCPBridge(self);self.analyzer=ProjectAnalyzer(self)
    def initGui(self):
        self.action=QAction("QGIS-IA-MAPS",self.iface.mainWindow());self.action.triggered.connect(self.show_dock);self.iface.addPluginToMenu("&QGIS-IA-MAPS",self.action);self.iface.addToolBarIcon(self.action)
    def unload(self):
        self.bridge.stop()
        if self.action:self.iface.removePluginMenu("&QGIS-IA-MAPS",self.action);self.iface.removeToolBarIcon(self.action)
        if self.dock:self.iface.removeDockWidget(self.dock);self.dock.deleteLater();self.dock=None
    def show_dock(self):
        if self.dock is None:
            self.dock=QDockWidget("QGIS-IA-MAPS",self.iface.mainWindow());panel=QWidget();layout=QVBoxLayout(panel);layout.addWidget(QLabel("Automação cartográfica e geração de mapas com IA"));self.status=QLabel("Status: pronto");layout.addWidget(self.status);self.log=QTextEdit();self.log.setReadOnly(True);layout.addWidget(self.log)
            for text,fn in [("Testar projeto atual",self.test_project),("Analisar projeto",self.analyze_project),("Analisar zoneamento (500 m)",self.analyze_zoning_500m),("Criar mapa A4",self.create_a4_map),("Iniciar/Parar ponte local",self.toggle_bridge)]:
                b=QPushButton(text);b.clicked.connect(fn);layout.addWidget(b)
            self.dock.setWidget(panel);self.iface.addDockWidget(2,self.dock)
        self.dock.show();self.dock.raise_()
    def log_message(self,msg):
        if self.log:self.log.append(str(msg))
    def toggle_bridge(self):
        try:
            if self.bridge.running:self.bridge.stop();self.status.setText("Status: ponte parada")
            else:self.bridge.start();self.status.setText(f"Status: ponte {self.bridge.host}:{self.bridge.port}")
            self.log_message("Ponte local: "+("ativa" if self.bridge.running else "parada"))
        except Exception as e:self.status.setText("Status: erro na ponte");self.log_message("ERRO: "+str(e))
    def project_info_layers(self):return list(QgsProject.instance().mapLayers().values())
    def project_info(self):
        p=QgsProject.instance();return {"path":p.fileName(),"title":p.title(),"layer_count":len(p.mapLayers()),"crs":p.crs().authid()}
    def _visible_canvas_layers(self):return list(self.iface.mapCanvas().layers())
    def list_layers(self):
        root=QgsProject.instance().layerTreeRoot();active={l.id() for l in self._visible_canvas_layers()};out=[]
        for l in QgsProject.instance().mapLayers().values():
            n=root.findLayer(l.id());out.append({"id":l.id(),"name":l.name(),"type":l.type(),"source":l.source(),"visible":bool(n and n.isVisible()),"active_in_canvas":l.id() in active,"crs":l.crs().authid() if l.crs().isValid() else None,"legend_name":title_from_name(l.name()),"classification":classify_layer(l)})
        return out
    def test_project(self):
        try:
            i=self.project_info();self.status.setText("Status: projeto lido");self.log_message("Projeto: "+(i["path"] or "(não salvo)"));self.log_message("Camadas: "+str(i["layer_count"]))
            for x in self.list_layers():self.log_message(f"- {x['name']} [{'ATIVA' if x['active_in_canvas'] else 'oculta'}] ({x['type']})")
        except Exception as e:self.status.setText("Status: erro");self.log_message("ERRO: "+str(e))
    def analyze_project(self):
        try:
            r=self.analyzer.analyze();self.status.setText("Status: projeto analisado");self.log_message(f"Análise: {r['active_layer_count']} camadas ativas.")
            for x in r["active_layers"]:self.log_message(f"- {x['name']} → {x['legend_name']} | {x['type']} | {x.get('interpretation',x.get('geometry',''))}")
            c=r["context"];self.log_message("Área objeto: "+(c["object_layer"] or "não identificada"));self.log_message("Zoneamento: "+(c["zoning_layer"] or "não identificado"));return r
        except Exception as e:self.status.setText("Status: erro na análise");self.log_message("ERRO: "+str(e));return None
    def analyze_zoning_500m(self):
        try:
            layers=self._visible_canvas_layers();active=self.iface.activeLayer();area=find_object_layer(layers,active_layer=active);z=find_zoning_layer(layers,exclude_layer=area)
            if area is None:raise ValueError("Área objeto não identificada. Selecione uma feição da área objeto e tente novamente.")
            if z is None:
                self.log_message("Camadas poligonais candidatas ao zoneamento:")
                for l in layers:
                    if l.type()==0 and l.geometryType()==QgsWkbTypes.PolygonGeometry and l.id()!=area.id():self.log_message(f"- {l.name()} | {l.featureCount()} feições | campos: {', '.join(f.name() for f in l.fields())}")
                raise ValueError("Não foi possível identificar automaticamente o zoneamento. A análise listou as candidatas no painel.")
            r=analyze_zoning(area,z,500,True);self.status.setText("Status: zoneamento analisado");self.log_message(f"Área: {r['area_layer']} | Zoneamento: {r['zoning_layer']} | Raio: 500 m")
            if not r["zoning"]:self.log_message("Nenhuma feição de zoneamento encontrada no raio de 500 m.")
            for x in r["zoning"]:self.log_message(f"- {x['zoning_name']} [{'NA ÁREA' if x['inside_object'] else str(x['distance_m'])+' m'}]")
            return r
        except Exception as e:self.status.setText("Status: erro no zoneamento");self.log_message("ERRO: "+str(e));return None
    def _legend_tree_for_active_layers(self):
        project=QgsProject.instance();active={l.id() for l in self._visible_canvas_layers()};root=project.layerTreeRoot().clone()
        for node in list(root.findLayers()):
            l=node.layer();keep=l is not None and l.id() in active and is_legend_candidate(l)
            if not keep:
                p=node.parent()
                if p is not None and QgsLayerTree.isGroup(p):QgsLayerTree.toGroup(p).removeChildNode(node)
            else:node.setName(title_from_name(l.name()));node.setUseLayerName(False)
        root.removeChildrenGroupWithoutLayers();return root
    def _polygon_layer_count(self):return sum(1 for l in self._visible_canvas_layers() if is_legend_candidate(l) and l.type()==0 and l.geometryType()==QgsWkbTypes.PolygonGeometry)
    def _legend_symbol_size(self):n=self._polygon_layer_count();return (8.0,4.0,n) if n<=4 else (4.0,2.0,n)
    def create_a4_map(self):self.create_layout("Mapa IA","A4","landscape");self.add_title("Mapa IA","MAPA GERADO PELO QGIS-IA-MAPS");self.add_legend("Mapa IA");self.add_scale("Mapa IA");self.status.setText("Status: mapa A4 criado");self.log_message("Mapa A4 criado.")
    def create_layout(self,name="Mapa IA",page="A4",orientation="landscape"):
        p=QgsProject.instance();old=p.layoutManager().layoutByName(name)
        if old:p.layoutManager().removeLayout(old)
        if page.upper()!="A4":raise ValueError("Somente A4.")
        w,h=(297,210) if orientation.lower()=="landscape" else (210,297);l=QgsPrintLayout(p);l.initializeDefaults();l.setName(name);l.pageCollection().page(0).setPageSize(QgsLayoutSize(w,h,QgsUnitTypes.LayoutMillimeters));p.layoutManager().addLayout(l)
        m=QgsLayoutItemMap(l);m.attemptMove(QgsLayoutPoint(10,18,QgsUnitTypes.LayoutMillimeters));m.attemptResize(QgsLayoutSize(w-80,h-48,QgsUnitTypes.LayoutMillimeters));m.setFrameEnabled(True);layers=self._visible_canvas_layers()
        if layers:m.setLayers(layers);e=self.iface.mapCanvas().extent();e.scale(1.05);m.setExtent(e)
        l.addLayoutItem(m);return {"name":name,"page":"A4","orientation":orientation.lower()}
    def _layout(self,name):
        l=QgsProject.instance().layoutManager().layoutByName(name)
        if not l:raise ValueError("Layout não encontrado: "+name)
        return l
    def _first_map(self,l):
        maps=[x for x in l.items() if isinstance(x,QgsLayoutItemMap)]
        if not maps:raise ValueError("Layout sem mapa")
        return maps[0]
    def add_title(self,name,text,size=14,x=10,y=5):
        l=self._layout(name);i=QgsLayoutItemLabel(l);i.setText(str(text));i.setFontPointSize(float(size));i.adjustSizeToText();i.attemptMove(QgsLayoutPoint(float(x),float(y),QgsUnitTypes.LayoutMillimeters));l.addLayoutItem(i);return True
    def add_legend(self,name,title="Legenda",x=225,y=18):
        l=self._layout(name);g=QgsLayoutItemLegend(l);g.setTitle(str(title));g.setLinkedMap(self._first_map(l));g.setAutoUpdateModel(False);g.model().setRootGroup(self._legend_tree_for_active_layers());w,h,n=self._legend_symbol_size();g.setSymbolWidth(w);g.setSymbolHeight(h);g.refresh();g.adjustBoxSize();g.attemptMove(QgsLayoutPoint(float(x),float(y),QgsUnitTypes.LayoutMillimeters));l.addLayoutItem(g);return {"success":True,"polygon_layer_count":n,"symbol_size_mm":{"width":w,"height":h}}
    def add_scale(self,name,x=10,y=185):
        l=self._layout(name);s=QgsLayoutItemScaleBar(l);s.setStyle("Single Box");s.setUnits(QgsUnitTypes.DistanceMeters);s.setNumberOfSegments(4);s.setNumberOfSegmentsLeft(0);s.setLinkedMap(self._first_map(l));s.attemptMove(QgsLayoutPoint(float(x),float(y),QgsUnitTypes.LayoutMillimeters));l.addLayoutItem(s);return True
    def export_layout(self,name,path,format="pdf"):
        l=self._layout(name);o=Path(path).expanduser();o.parent.mkdir(parents=True,exist_ok=True);e=QgsLayoutExporter(l);f=str(format).lower();r=e.exportToPdf(str(o),QgsLayoutExporter.PdfExportSettings()) if f=="pdf" else e.exportToImage(str(o),QgsLayoutExporter.ImageExportSettings()) if f=="png" else None
        if r!=QgsLayoutExporter.Success:raise RuntimeError("Falha na exportação")
        return {"success":True,"path":str(o)}
    def save_project(self,path=None):
        p=QgsProject.instance()
        if path:p.setFileName(str(Path(path).expanduser()))
        if not p.write():raise RuntimeError("Falha ao salvar projeto")
        return {"success":True,"path":p.fileName()}
