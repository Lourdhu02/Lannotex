from collections import OrderedDict
from pathlib import Path
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, QSize
from PySide6.QtGui import QColor


class ImageListModel(QAbstractListModel):
    """Virtual list: at most eight pages of 128 metadata records in memory."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.search = ''
        self.status = 'all'
        self.total = 0
        self.pages = OrderedDict()

    def refresh(self, project=None, search=None, status=None):
        self.beginResetModel()
        if project is not None: self.project = project
        if search is not None: self.search = search
        if status is not None: self.status = status
        self.pages.clear()
        self.total = self.project.query(self.search,self.status,count=True) if self.project else 0
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else self.total

    def record(self, row):
        if not 0 <= row < self.total: return None
        page = row//128
        if page not in self.pages:
            self.pages[page] = self.project.query(self.search,self.status,offset=page*128)
            while len(self.pages)>8: self.pages.popitem(last=False)
        self.pages.move_to_end(page)
        return self.pages[page][row%128]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        if role == Qt.SizeHintRole: return QSize(200,58)
        row = self.record(index.row())
        if row is None: return None
        if role == Qt.DisplayRole:
            state = {'new':'Unlabeled', 'done':'Labeled', 'empty':'No targets'}.get(row['status'],row['status'])
            return f"{Path(row['path']).name}\n{state}  ·  {row['width']} × {row['height']}"
        if role == Qt.ToolTipRole: return row['path']
        if role == Qt.ForegroundRole and row['status'] != 'new': return QColor('#888888')
        if role == Qt.UserRole: return dict(row)

    def invalidate(self):
        self.pages.clear()
        if self.total: self.dataChanged.emit(self.index(0),self.index(self.total-1))
