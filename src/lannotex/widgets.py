"""Small reusable pieces of the workspace UI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QListWidget, QToolButton, QVBoxLayout, QWidget


class Section(QWidget):
    """A titled group that can be folded away.

    Sections are anchored to the top of their column with a stretch beneath, so folding one
    never shifts the others, and a panel never buries its controls below the fold.
    """

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.header = QToolButton()
        self.header.setObjectName("sectionHeader")
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setText(title)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setArrowType(Qt.DownArrow)
        self.header.setSizePolicy(self.header.sizePolicy().horizontalPolicy(), self.header.sizePolicy().verticalPolicy())
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.toggled.connect(self._toggled)
        layout.addWidget(self.header)
        self.body = QFrame()
        self.body.setObjectName("sectionBody")
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(0, 0, 0, 4)
        self.content.setSpacing(7)
        layout.addWidget(self.body)

    def _toggled(self, open_: bool) -> None:
        self.header.setArrowType(Qt.DownArrow if open_ else Qt.RightArrow)
        self.body.setVisible(open_)

    def add(self, item) -> None:
        if isinstance(item, QWidget):
            self.content.addWidget(item)
        else:
            self.content.addLayout(item)

    def set_open(self, open_: bool) -> None:
        self.header.setChecked(open_)

    def set_title(self, title: str) -> None:
        self.header.setText(title)


def fit_list(view: QListWidget, visible_rows: int = 8, minimum_rows: int = 1) -> None:
    """Size a list to its contents so the panel scrolls, not the list inside it.

    A second scrollbar inside a scrolling panel is the fastest way to lose a control, so the
    list only grows its own scrollbar once it is longer than `visible_rows`.
    """
    count = view.count()
    row = view.sizeHintForRow(0) if count else 24
    if row <= 0:
        row = 24
    rows = max(minimum_rows, min(count, visible_rows))
    frame = 2 * view.frameWidth() + 2
    view.setFixedHeight(rows * row + frame)
    crowded = count > visible_rows
    view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if crowded else Qt.ScrollBarAlwaysOff)
