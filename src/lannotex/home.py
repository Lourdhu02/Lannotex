"""Home, recent projects and intentional pipeline setup, independent of editor logic."""
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout, QWidget)

PIPELINES = {
    'classification': ('Classification', 'Assign classes to whole images. No drawing tools.', ['classification']),
    'detection': ('Object detection', 'Locate objects with editable bounding boxes.', ['box']),
    'segmentation': ('Segmentation', 'Trace precise regions with polygon vertices.', ['polygon']),
    'combined': ('Combined pipeline', 'Classes, bounding boxes and polygons together.', ['classification','box','polygon']),
}


def text(value, role='muted'):
    widget=QLabel(value); widget.setObjectName(role); widget.setWordWrap(True); return widget


def pipeline_card(title,description):
    card=QPushButton(); card.setObjectName('pipeline')
    card.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred); card.setMinimumWidth(160)
    layout=QVBoxLayout(card); layout.setContentsMargins(18,16,18,16); layout.setSpacing(8)
    for content,role in [(title+'  ↗','cardTitle'),(description,'muted')]:
        item=text(content,role); item.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(item)
    card.setAccessibleName(title); return card


class Home(QWidget):
    create_requested=Signal(str)
    open_requested=Signal()
    continue_requested=Signal(str)
    join_requested=Signal()
    theme_requested=Signal()
    preferences_requested=Signal()

    def __init__(self):
        super().__init__(); self.setObjectName('home')
        shell=QHBoxLayout(self); shell.setContentsMargins(0,0,0,0); shell.setSpacing(0)
        rail=QWidget(); rail.setObjectName('rail'); rail.setFixedWidth(220); nav=QVBoxLayout(rail)
        nav.setContentsMargins(16,28,16,20); nav.setSpacing(8)
        nav.addWidget(text('◈  Lannotex','brand')); nav.addSpacing(36)
        for title,signal in [('＋  New project',lambda:self.create_requested.emit('classification')),
                             ('▤  Open project',self.open_requested.emit),('↗  Join team',self.join_requested.emit)]:
            b=QPushButton(title); b.setObjectName('nav'); b.clicked.connect(signal); nav.addWidget(b)
        nav.addStretch(); nav.addWidget(text('YOUR WORKSPACE\nSolo or together. Your data.'))
        b=QPushButton('◐  Light / dark'); b.setObjectName('nav'); b.clicked.connect(self.theme_requested); nav.addWidget(b)
        b=QPushButton('Settings && shortcuts'); b.setObjectName('nav'); b.clicked.connect(self.preferences_requested); nav.addWidget(b)
        shell.addWidget(rail)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(52,38,52,28); layout.setSpacing(18)
        layout.addStretch(1); layout.addWidget(text('A little more clarity.\nA lot better data.','hero'))
        layout.addWidget(text('Choose your workflow. Pick up where you left off.','subtitle')); layout.addSpacing(12)
        grid=QGridLayout(); grid.setSpacing(12)
        for i,(key,(title,description,_)) in enumerate(PIPELINES.items()):
            card=pipeline_card(title,description)
            card.setToolTip(description); card.clicked.connect(lambda checked=False,k=key:self.create_requested.emit(k))
            grid.addWidget(card,i//2,i%2)
        layout.addLayout(grid); layout.addSpacing(14)
        row=QHBoxLayout(); row.addWidget(text('Continue working','cardTitle')); row.addStretch()
        self.continue_button=QPushButton('Continue  →'); self.continue_button.setObjectName('primary')
        self.continue_button.clicked.connect(self.resume); row.addWidget(self.continue_button)
        b=QPushButton('Open another…'); b.clicked.connect(self.open_requested); row.addWidget(b); layout.addLayout(row)
        self.recents=QListWidget(); self.recents.setMinimumHeight(130); self.recents.setMaximumHeight(260)
        self.recents.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.recents.setTextElideMode(Qt.ElideMiddle)
        self.recents.itemDoubleClicked.connect(lambda item:self.continue_requested.emit(item.data(Qt.UserRole)))
        layout.addWidget(self.recents)
        self.empty=text('No recent projects yet. Create your first project above.'); layout.addWidget(self.empty)
        layout.addStretch(1)
        layout.addWidget(text('Solo projects work offline. Team projects connect only to the host you choose.'))
        scroll.setWidget(page); shell.addWidget(scroll,1)

    def refresh(self, recent):
        self.recents.clear()
        for path in recent:
            exists=(Path(path)/'project.sqlite3').is_file()
            item=QListWidgetItem(f"{Path(path).name}{'' if exists else ' · unavailable'}\n{path}")
            item.setData(Qt.UserRole,path); self.recents.addItem(item)
        if self.recents.count(): self.recents.setCurrentRow(0)
        self.empty.setVisible(not self.recents.count()); self.continue_button.setEnabled(bool(self.recents.count()))

    def resume(self):
        item=self.recents.currentItem()
        if item: self.continue_requested.emit(item.data(Qt.UserRole))


class CreateProjectDialog(QDialog):
    def __init__(self, pipeline='classification', parent=None):
        super().__init__(parent); self.setWindowTitle('Create a project'); self.resize(680,650)
        layout=QVBoxLayout(self); layout.setContentsMargins(28,24,28,24); layout.setSpacing(12)
        layout.addWidget(text('Make room for your next dataset.','cardTitle'))
        self.name=QLineEdit(); self.name.setPlaceholderText('Project name'); layout.addWidget(self.name)
        location=QHBoxLayout(); self.location=QLineEdit(); self.location.setPlaceholderText('Parent folder for the project')
        location.addWidget(self.location); browse=QPushButton('Browse…'); browse.clicked.connect(self.browse); location.addWidget(browse); layout.addLayout(location)
        self.pipelines=QButtonGroup(self); self.pipelines.setExclusive(True); grid=QGridLayout()
        self.buttons={}
        for i,(key,(title,description,_)) in enumerate(PIPELINES.items()):
            b=pipeline_card(title,description); b.setCheckable(True)
            self.pipelines.addButton(b); self.buttons[key]=b; grid.addWidget(b,i//2,i%2)
        self.buttons[pipeline].setChecked(True); layout.addLayout(grid)
        self.mode=QComboBox(); self.mode.addItem('Solo · just me','solo'); self.mode.addItem('Team · simultaneous reviewers on different computers','team')
        layout.addWidget(text('Who is working on this project?')); layout.addWidget(self.mode)
        self.classes=QTextEdit(); self.classes.setPlaceholderText('Classes / object labels, one per line\nYou can also add them later.'); self.classes.setMaximumHeight(100); layout.addWidget(self.classes)
        layout.addWidget(text('Team mode uses this computer as the project host. You control who can connect.'))
        buttons=QDialogButtonBox(QDialogButtonBox.Cancel); create=buttons.addButton('Create project',QDialogButtonBox.AcceptRole)
        create.setObjectName('primary'); buttons.accepted.connect(self.validate); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def browse(self):
        path=QFileDialog.getExistingDirectory(self,'Choose parent folder')
        if path: self.location.setText(path)

    def validate(self):
        name=self.name.text().strip()
        if not name or name in ('.','..') or any(c in name for c in '<>:"/\\|?*') or name.endswith(('.', ' ')):
            QMessageBox.warning(self,'Project name','Enter a valid folder name.'); return
        if not Path(self.location.text()).is_dir() or not self.location.text().strip():
            QMessageBox.warning(self,'Project location','Choose an existing parent folder.'); return
        if self.folder.exists() and any(self.folder.iterdir()):
            QMessageBox.warning(self,'Folder already exists','Choose a new name; this folder is not empty.'); return
        labels=[s.strip() for s in self.classes.toPlainText().splitlines() if s.strip()]
        if len(labels)!=len(set(labels)) or any(len(s)>120 for s in labels):
            QMessageBox.warning(self,'Labels','Use unique labels of 1–120 characters.'); return
        self.accept()

    @property
    def folder(self): return Path(self.location.text())/self.name.text().strip()

    @property
    def pipeline(self): return next(key for key,b in self.buttons.items() if b.isChecked())
