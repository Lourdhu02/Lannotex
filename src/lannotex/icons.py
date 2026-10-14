"""Line icons drawn on a 24-unit grid, rendered in the current theme's text color."""
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    'home': '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    'select': '<path d="M5 3l13 7.5-5.5 1.8L10 18z"/><path d="M12.5 12.3 17 19"/>',
    'box': '<rect x="4" y="5" width="16" height="14" rx="1.5"/><path d="M4 9h2M18 9h2M4 15h2M18 15h2"/>',
    'polygon': '<path d="M6.5 18.5 3.5 9.5l8-6 9 6.5-3.5 8.5z"/><circle cx="6.5" cy="18.5" r="1.3"/><circle cx="3.5" cy="9.5" r="1.3"/><circle cx="11.5" cy="3.5" r="1.3"/><circle cx="20.5" cy="10" r="1.3"/><circle cx="17" cy="18.5" r="1.3"/>',
    'undo': '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    'redo': '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
    'fit': '<path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/>',
    'theme': '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5a8.5 8.5 0 0 0 0 17z" fill="CURRENT"/>',
    'prev': '<path d="m15 18-6-6 6-6"/>',
    'next': '<path d="m9 18 6-6-6-6"/>',
    'folder-plus': '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/><path d="M12 11v6M9 14h6"/>',
    'file-plus': '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M12 11v6M9 14h6"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'folder-open': '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2V11"/><path d="M3 7v11.5h15.5L21 11H6.5z"/>',
    'users': '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18.5 14.5a6.5 6.5 0 0 1 3 5.5"/>',
    'settings': '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
    'export': '<path d="M12 15V3M7 8l5-5 5 5"/><path d="M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/>',
    'chart': '<path d="M4 20V10M10 20V4M16 20v-7M2.5 20.5h19"/>',
    'save': '<path d="M5 3h11l4 4v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a1 1 0 0 1 1-2z"/><path d="M8 3v5h7V3M8 21v-7h8v7"/>',
}


LOGO = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'
        '<rect x="1" y="1" width="126" height="126" rx="27" fill="#141414" stroke="#ffffff" stroke-opacity=".14" stroke-width="2"/>'
        '<path d="M28 50V28h22M78 28h22v22M100 78v22H78M50 100H28V78" fill="none" stroke="#fafafa" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M47 80 61 45l25 14-7 26z" fill="#37b8a5" fill-opacity=".3" stroke="#37b8a5" stroke-width="4" stroke-linejoin="round"/>'
        '<g fill="#fafafa" stroke="#37b8a5" stroke-width="3"><circle cx="47" cy="80" r="5"/><circle cx="61" cy="45" r="5"/>'
        '<circle cx="86" cy="59" r="5"/><circle cx="79" cy="85" r="5"/></g></svg>')


def render(markup, size):
    renderer = QSvgRenderer(QByteArray(markup.encode()))
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied); image.fill(Qt.transparent)
    painter = QPainter(image); renderer.render(painter, QRectF(0, 0, size, size)); painter.end()
    return QPixmap.fromImage(image)


def logo(size=64):
    return QIcon(render(LOGO, size))


def svg(name, color):
    body = PATHS[name].replace('CURRENT', color)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def icon(name, color, size=64):
    return QIcon(render(svg(name, color), size))
