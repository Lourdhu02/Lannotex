from PySide6.QtGui import QColor, QPalette


def apply_theme(app, dark=True):
    bg, panel, raised = ('#1d232c','#242c37','#303b49') if dark else ('#f2f4f7','#ffffff','#e7edf2')
    text, muted, border = ('#e6edf5','#9caebe','#384656') if dark else ('#202c38','#526678','#d7dfe6')
    accent = '#37b8a5' if dark else '#187f70'
    palette=QPalette()
    for role,color in [(QPalette.Window,bg),(QPalette.WindowText,text),(QPalette.Base,panel),
                       (QPalette.AlternateBase,raised),(QPalette.Text,text),(QPalette.Button,panel),
                       (QPalette.ButtonText,text),(QPalette.Highlight,accent),(QPalette.HighlightedText,'#ffffff'),
                       (QPalette.ToolTipBase,panel),(QPalette.ToolTipText,text)]: palette.setColor(role,QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(f'''
        QWidget {{ font-family: "Segoe UI"; font-size: 10pt; color: {text}; }}
        QMainWindow, QDialog {{ background: {bg}; }}
        QFrame#header {{ background:{panel}; border-bottom:1px solid {border}; }}
        QFrame#panel, QScrollArea {{ background:{panel}; border:1px solid {border}; border-radius:8px; }}
        QLabel#brand {{ font-size:19pt; font-weight:700; }}
        QLabel#section {{ color:{muted}; font-size:9pt; font-weight:600; padding-top:8px; }}
        QLabel#muted {{ color:{muted}; }}
        QLabel#save {{ color:{accent}; padding:6px 12px; background:{raised}; border-radius:6px; }}
        QPushButton, QToolButton {{ background:{panel}; border:1px solid {border}; border-radius:5px; padding:7px 11px; }}
        QPushButton:hover, QToolButton:hover {{ background:{raised}; border-color:{muted}; }}
        QPushButton:pressed, QToolButton:checked {{ background:{raised}; border-color:{accent}; color:{accent}; }}
        QPushButton#primary {{ background:{accent}; border-color:{accent}; color:white; font-weight:600; }}
        QPushButton#danger {{ color:#df8b87; }}
        QPushButton:disabled, QToolButton:disabled {{ color:{muted}; border-color:{border}; }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit {{ background:{bg}; border:1px solid {border}; border-radius:5px; padding:7px; selection-background-color:{accent}; }}
        QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {{ border-color:{accent}; }}
        QComboBox::drop-down {{ border:0; width:20px; }}
        QListView, QListWidget, QTableWidget, QTextEdit {{ background:{panel}; border:0; outline:0; }}
        QListView::item, QListWidget::item {{ border-bottom:1px solid {border}; padding:6px; }}
        QListView::item:selected, QListWidget::item:selected {{ background:{raised}; color:{text}; border-left:3px solid {accent}; }}
        QListView::item:hover {{ background:{raised}; }}
        QSplitter::handle {{ background:{bg}; width:8px; }}
        QMenuBar, QMenu {{ background:{panel}; }}
        QMenuBar::item:selected, QMenu::item:selected {{ background:{raised}; }}
        QMenu::item {{ padding:7px 26px; }}
        QStatusBar {{ background:{panel}; border-top:1px solid {border}; }}
        QStatusBar::item {{ border:0; }}
        QScrollBar:vertical {{ background:{panel}; width:9px; margin:0; }}
        QScrollBar::handle:vertical {{ background:{border}; min-height:30px; border-radius:4px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        QProgressBar {{ border:0; background:{raised}; border-radius:4px; text-align:center; }}
        QProgressBar::chunk {{ background:{accent}; border-radius:4px; }}
        QCheckBox {{ spacing:7px; padding:4px 0; }}
        QToolTip {{ background:{panel}; color:{text}; border:1px solid {border}; padding:6px; }}
    ''')
