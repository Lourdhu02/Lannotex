"""Background thumbnails with a disk cache outside the project folder."""
from collections import OrderedDict
import hashlib
import itertools
import os
from pathlib import Path
import tempfile
from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QStandardPaths, QThreadPool, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap
from .workers import Job, to_qimage

EDGE = 128
DISK_BUDGET = 512 * 1024 * 1024


def cache_dir():
    override = os.environ.get('LANNOTEX_CACHE_DIR')
    base = Path(override) if override else Path(QStandardPaths.writableLocation(QStandardPaths.GenericCacheLocation)) / 'Lannotex'
    return base / 'thumbnails'


def thumbnail_file(folder, path):
    stat = Path(path).stat()
    digest = hashlib.sha1(f'{Path(path).resolve()}|{stat.st_mtime_ns}|{stat.st_size}'.encode()).hexdigest()
    return Path(folder) / digest[:2] / f'{digest}.jpg'


def make_thumbnail(folder, path, edge=EDGE):
    """Return a QImage thumbnail, creating the cached JPEG on first use."""
    target = thumbnail_file(folder, path)
    if target.is_file():
        with Image.open(target) as cached: return to_qimage(cached)
    with Image.open(path) as image:
        image.draft('RGB', (edge, edge))
        image = ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(suffix='.jpg', dir=target.parent); os.close(fd)
    try:
        image.save(temp, 'JPEG', quality=82); os.replace(temp, target)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return to_qimage(image)


def prune(folder, budget=DISK_BUDGET):
    """Delete least-recently-modified thumbnails until the cache fits the budget."""
    files = [(f.stat().st_mtime, f.stat().st_size, f) for f in Path(folder).glob('*/*.jpg')]
    total = sum(size for _, size, _ in files)
    for _, size, f in sorted(files):
        if total <= budget: break
        try: f.unlink(); total -= size
        except OSError: pass
    return total


class Thumbnails(QObject):
    """Most recently requested thumbnails are generated first, so the visible rows win while scrolling."""
    ready = Signal(str)

    def __init__(self, parent=None, folder=None, memory=600):
        super().__init__(parent)
        self.folder = Path(folder) if folder else cache_dir()
        self.pool = QThreadPool(self); self.pool.setMaxThreadCount(2)
        self.memory = OrderedDict(); self.limit = memory
        self.pending = set(); self.order = itertools.count()

    def prune_later(self, budget=DISK_BUDGET):
        folder = self.folder
        self.pool.start(Job(lambda cancel, progress: prune(folder, budget)), -1)

    def get(self, path):
        key = str(path)
        if key in self.memory:
            self.memory.move_to_end(key); return self.memory[key]
        if key not in self.pending:
            self.pending.add(key)
            folder = self.folder
            def work(cancel, progress):
                try: return key, make_thumbnail(folder, key)
                except Exception: return key, None  # unreadable image: remember "no thumbnail", don't retry
            job = Job(work)
            job.events.result.connect(self._done)
            self.pool.start(job, next(self.order))
        return None

    @Slot(object)
    def _done(self, payload):
        key, image = payload
        # QIcon (not QPixmap) so the view scales it to its iconSize on any display density.
        self._store(key, QIcon(QPixmap.fromImage(image)) if image is not None else None)

    def _store(self, key, pixmap):
        self.pending.discard(key)
        self.memory[key] = pixmap
        while len(self.memory) > self.limit: self.memory.popitem(last=False)
        self.ready.emit(key)

    def clear(self):
        self.memory.clear()
