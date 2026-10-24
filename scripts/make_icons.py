"""Build the platform icon files from docs/assets/logo.svg, the one source of truth.

Run after changing the logo:

    python scripts/make_icons.py
"""
import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs' / 'assets' / 'logo.svg'
OUT = ROOT / 'assets'
# Windows Explorer and the taskbar pick from these; macOS wants the whole ladder up to 1024.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICNS_SIZES = (16, 32, 64, 128, 256, 512, 1024)


def rasterize(renderer, size):
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    buffer = QBuffer()
    buffer.open(QBuffer.ReadWrite)
    image.save(buffer, 'PNG')
    return Image.open(io.BytesIO(bytes(buffer.data())))


def main():
    QGuiApplication(sys.argv)
    renderer = QSvgRenderer(QByteArray(SOURCE.read_bytes()))
    if not renderer.isValid():
        raise SystemExit(f'{SOURCE} is not valid SVG')
    OUT.mkdir(exist_ok=True)
    frames = {size: rasterize(renderer, size) for size in sorted({*ICO_SIZES, *ICNS_SIZES})}
    frames[max(frames)].save(OUT / 'Lannotex.ico', sizes=[(s, s) for s in ICO_SIZES])
    frames[1024].save(OUT / 'Lannotex.icns')
    frames[512].save(OUT / 'Lannotex.png')
    for name in ('Lannotex.ico', 'Lannotex.icns', 'Lannotex.png'):
        print(f'wrote assets/{name}')


if __name__ == '__main__':
    main()
