"""Disk-cached tile pyramids so an image of any size can be viewed at full resolution.

A pyramid holds the source at 1:1 as level 0 and each coarser level at half the previous
size, cut into 512 px tiles. The canvas only ever holds the tiles it is showing, so memory
follows the size of the window rather than the size of the image.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections import OrderedDict
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtGui import QImage, QPainter

from .workers import to_qimage, to_rgb

TILE = 512
QUALITY = 92
MEMORY_BUDGET = 128 * 1024 * 1024
DISK_BUDGET = 4 * 1024 * 1024 * 1024


def cache_dir() -> Path:
    from PySide6.QtCore import QStandardPaths

    override = os.environ.get("LANNOTEX_CACHE_DIR")
    base = (
        Path(override)
        if override
        else Path(QStandardPaths.writableLocation(QStandardPaths.GenericCacheLocation)) / "Lannotex"
    )
    return base / "pyramids"


def pyramid_key(path: str | os.PathLike) -> str:
    stat = Path(path).stat()
    seed = f"{Path(path).resolve()}|{stat.st_mtime_ns}|{stat.st_size}|{TILE}|{QUALITY}"
    return hashlib.sha1(seed.encode()).hexdigest()


def levels_for(width: int, height: int) -> int:
    """Enough levels that the coarsest fits in a single tile."""
    count = 1
    size = max(width, height)
    while size > TILE:
        size //= 2
        count += 1
    return count


class Pyramid:
    def __init__(self, path, width: int, height: int, root: Path) -> None:
        self.path = str(path)
        self.width = int(width)
        self.height = int(height)
        self.levels = levels_for(self.width, self.height)
        self.folder = Path(root) / pyramid_key(path)
        self._done: set[int] = set()
        self._load_manifest()

    # ---- geometry -------------------------------------------------------
    def level_size(self, level: int) -> tuple[int, int]:
        factor = 2**level
        return max(1, self.width // factor), max(1, self.height // factor)

    def grid(self, level: int) -> tuple[int, int]:
        w, h = self.level_size(level)
        return (w + TILE - 1) // TILE, (h + TILE - 1) // TILE

    def level_for_scale(self, scale: float) -> int:
        """Pick the level whose pixels are closest to screen pixels without going under."""
        level = 0
        while level + 1 < self.levels and scale <= 1 / (2 ** (level + 1)):
            level += 1
        return level

    def preview_level(self, max_edge: int = 2560) -> int:
        """The finest level that still fits a quick whole-image preview."""
        for level in range(self.levels):
            w, h = self.level_size(level)
            if max(w, h) <= max_edge:
                return level
        return self.levels - 1

    def compose(self, level: int) -> QImage | None:
        """Stitch one whole level into a single image, for use as an instant preview."""
        if not self.has_level(level):
            return None
        width, height = self.level_size(level)
        cols, rows = self.grid(level)
        canvas = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        canvas.fill(0)
        painter = QPainter(canvas)
        try:
            for row in range(rows):
                for col in range(cols):
                    try:
                        with Image.open(self.tile_path(level, col, row)) as tile:
                            painter.drawImage(col * TILE, row * TILE, to_qimage(tile))
                    except (OSError, ValueError):
                        return None
        finally:
            painter.end()
        return canvas

    # ---- disk -----------------------------------------------------------
    @property
    def manifest(self) -> Path:
        return self.folder / "levels.json"

    def _load_manifest(self) -> None:
        try:
            data = json.loads(self.manifest.read_text(encoding="utf-8"))
            if data.get("width") == self.width and data.get("height") == self.height:
                self._done = {int(v) for v in data.get("levels", ())}
        except (OSError, ValueError):
            self._done = set()

    def _save_manifest(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        payload = {"width": self.width, "height": self.height, "levels": sorted(self._done)}
        fd, temp = tempfile.mkstemp(dir=self.folder, suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
        os.replace(temp, self.manifest)

    def complete(self) -> bool:
        return len(self._done) == self.levels

    def has_level(self, level: int) -> bool:
        return level in self._done

    def tile_path(self, level: int, col: int, row: int) -> Path:
        return self.folder / f"L{level}" / f"{col}_{row}.jpg"

    # ---- building -------------------------------------------------------
    def build(self, cancel, progress) -> dict:
        """Cut every level to disk, finest first. Safe to re-run; finished levels are skipped."""
        if self.complete():
            return {"levels": self.levels, "skipped": True}
        self.folder.mkdir(parents=True, exist_ok=True)
        written = 0
        with Image.open(self.path) as source:
            # Rotate and convert only when the file actually needs it: at this size every
            # needless copy of the decoded image costs gigabytes.
            image = source
            if source.getexif().get(274, 1) in (2, 3, 4, 5, 6, 7, 8):
                image = ImageOps.exif_transpose(source)
            if image.mode != "RGB":
                image = to_rgb(image)
            else:
                image.load()
            for level in range(self.levels):
                if cancel.is_set():
                    break
                if level:
                    smaller = image.reduce(2)
                    if image is not source:
                        image.close()
                    image = smaller
                if level in self._done:
                    continue
                written += self._cut(image, level, cancel)
                if cancel.is_set():
                    break
                self._done.add(level)
                self._save_manifest()
                progress(round((level + 1) / self.levels * 100), f"Prepared zoom level {level + 1} of {self.levels}")
            if image is not source:
                image.close()
        return {"levels": self.levels, "tiles": written, "cancelled": cancel.is_set()}

    def _cut(self, image: Image.Image, level: int, cancel) -> int:
        folder = self.folder / f"L{level}"
        folder.mkdir(parents=True, exist_ok=True)
        cols, rows = self.grid(level)
        written = 0
        for row in range(rows):
            if cancel.is_set():
                return written
            for col in range(cols):
                target = folder / f"{col}_{row}.jpg"
                if target.exists():
                    continue
                box = (col * TILE, row * TILE, min((col + 1) * TILE, image.width), min((row + 1) * TILE, image.height))
                if box[2] <= box[0] or box[3] <= box[1]:
                    continue
                fd, temp = tempfile.mkstemp(dir=folder, suffix=".jpg")
                os.close(fd)
                image.crop(box).save(temp, "JPEG", quality=QUALITY, subsampling=0)
                os.replace(temp, target)
                written += 1
        return written


def prune(root: Path, budget: int = DISK_BUDGET) -> int:
    """Drop the least recently used pyramids until the cache fits its budget."""
    folders = []
    total = 0
    for folder in Path(root).glob("*"):
        if not folder.is_dir():
            continue
        size = sum(f.stat().st_size for f in folder.rglob("*.jpg"))
        folders.append((folder.stat().st_mtime, size, folder))
        total += size
    for _, size, folder in sorted(folders):
        if total <= budget:
            break
        shutil.rmtree(folder, ignore_errors=True)
        total -= size
    return total


class TileCache:
    """Decoded tiles, bounded by bytes and keyed by (pyramid folder, level, col, row)."""

    def __init__(self, budget: int = MEMORY_BUDGET) -> None:
        self._entries: OrderedDict[tuple, QImage] = OrderedDict()
        self._bytes = 0
        self.budget = budget

    def clear(self) -> None:
        self._entries.clear()
        self._bytes = 0

    def get(self, pyramid: Pyramid, level: int, col: int, row: int) -> QImage | None:
        key = (str(pyramid.folder), level, col, row)
        hit = self._entries.get(key)
        if hit is not None:
            self._entries.move_to_end(key)
            return hit
        path = pyramid.tile_path(level, col, row)
        try:
            with Image.open(path) as tile:
                image = to_qimage(tile)
        except (OSError, ValueError):
            return None
        self._entries[key] = image
        self._bytes += image.sizeInBytes()
        while self._entries and self._bytes > self.budget:
            _, dropped = self._entries.popitem(last=False)
            self._bytes -= dropped.sizeInBytes()
        return image
