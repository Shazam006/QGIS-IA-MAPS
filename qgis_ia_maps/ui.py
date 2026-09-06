from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox, QTabWidget, QTextEdit, QFrame


def button(text, slot, primary=False):
    b = QPushButton(text)
    b.setMinimumHeight(36)
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(slot)
    if primary:
        b.setObjectName("primary")
    return b


def card(title, subtitle=None):
    box = QGroupBox(title)
    box.setObjectName("card")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(12, 12, 12, 12)
    lay.setSpacing(8)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("muted")
        s.setWordWrap(True)
        lay.addWidget(s)
    return box, lay


def apply_style(widget):
    widget.setStyleSheet("""
    QDockWidget, QWidget { background: #f6f8fa; }
    QLabel#title { font-size: 17pt; font-weight: 700; color: #17202a; }
    QLabel#subtitle, QLabel#muted { color: #667085; }
    QLabel#status { font-weight: 600; color: #344054; }
    QLabel#dot { color: #12b76a; font-size: 12pt; }
    QLabel#metric { font-size: 14pt; font-weight: 700; color: #101828; }
    QGroupBox#card { background: #ffffff; border: 1px solid #d0d5dd; border-radius: 8px; margin-top: 8px; font-weight: 700; color: #344054; }
    QGroupBox#card::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; background: #f6f8fa; }
    QPushButton { background: #ffffff; border: 1px solid #d0d5dd; border-radius: 6px; padding: 7px 10px; color: #344054; }
    QPushButton:hover { background: #f2f4f7; border-color: #98a2b3; }
    QPushButton#primary { background: #175cd3; color: #ffffff; border: 1px solid #175cd3; font-weight: 700; }
    QPushButton#primary:hover { background: #1849a9; }
    QTabWidget::pane { border: 0; }
    QTabBar::tab { padding: 8px 13px; color: #667085; }
    QTabBar::tab:selected { color: #175cd3; font-weight: 700; border-bottom: 2px solid #175cd3; }
    QTextEdit#log { background: #101828; color: #e4e7ec; border: 0; border-radius: 6px; font-family: Consolas; font-size: 9pt; }
    """)
