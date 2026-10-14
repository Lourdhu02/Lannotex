"""Ctrl+K command palette: fuzzy-search every menu command and run it from the keyboard."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout


def menu_commands(menubar):
    """(title, shortcut, action) for every enabled command, with its menu path for context."""
    found = []
    def walk(menu, path):
        for action in menu.actions():
            if action.isSeparator(): continue
            if action.menu(): walk(action.menu(), path + [action.text().replace('&', '')]); continue
            text, _, shortcut = action.text().partition('\t')
            title = text.replace('&&', '\0').replace('&', '').replace('\0', '&')
            found.append((title, shortcut or action.shortcut().toString(), ' › '.join(path), action))
    for top in menubar.actions():
        if top.menu(): walk(top.menu(), [top.text().replace('&', '')])
    return found


def score(query, title, path):
    """Lower is better; None = no match. Prefix > word start > substring > all words present."""
    q, t = query.lower().strip(), title.lower()
    if not q: return 0
    if t.startswith(q): return 0
    if any(word.startswith(q) for word in t.split()): return 1
    if q in t: return 2
    haystack = f'{t} {path.lower()}'
    return 3 if all(word in haystack for word in q.split()) else None


class CommandPalette(QDialog):
    def __init__(self, parent, commands):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setObjectName('palette'); self.setModal(True); self.resize(580, 400)
        self.commands = commands
        layout = QVBoxLayout(self); layout.setContentsMargins(10, 10, 10, 10); layout.setSpacing(8)
        self.query = QLineEdit(); self.query.setPlaceholderText('Type a command…  (Enter runs it, Esc closes)')
        self.query.setAccessibleName('Command search'); layout.addWidget(self.query)
        self.results = QListWidget(); self.results.setAccessibleName('Matching commands'); layout.addWidget(self.results)
        self.query.textChanged.connect(self.refresh)
        self.query.returnPressed.connect(self.run)
        self.results.itemActivated.connect(lambda _: self.run())
        self.query.installEventFilter(self)
        self.refresh()
        if parent: self.move(parent.mapToGlobal(parent.rect().center()).x() - self.width()//2, parent.mapToGlobal(parent.rect().topLeft()).y() + 90)

    def refresh(self):
        self.results.clear()
        ranked = []
        for title, shortcut, path, action in self.commands:
            rank = score(self.query.text(), title, path)
            if rank is not None: ranked.append((rank, title.lower(), title, shortcut, path, action))
        for _, _, title, shortcut, path, action in sorted(ranked, key=lambda r: r[:2]):
            item = QListWidgetItem(f'{title}\n{path}' + (f'   ·   {shortcut}' if shortcut else ''))
            item.setData(Qt.UserRole, action)
            if not action.isEnabled(): item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.results.addItem(item)
        for row in range(self.results.count()):
            if self.results.item(row).flags() & Qt.ItemIsEnabled: self.results.setCurrentRow(row); break

    def eventFilter(self, obj, event):
        if obj is self.query and event.type() == event.Type.KeyPress and event.key() in (Qt.Key_Down, Qt.Key_Up, Qt.Key_PageDown, Qt.Key_PageUp):
            self.results.keyPressEvent(event); return True
        return super().eventFilter(obj, event)

    def run(self):
        item = self.results.currentItem()
        if item is None or not item.flags() & Qt.ItemIsEnabled: return
        action = item.data(Qt.UserRole)
        self.accept()
        action.trigger()
