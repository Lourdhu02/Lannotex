"""Cancellable I/O jobs and serial, bounded background image decoding."""
from collections import OrderedDict
import os
from pathlib import Path
import threading
import time
from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage
from .storage import Project

FORMATS = {'.jpg', '.jpeg', '.png', '.webp'}


class Events(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)
    finished = Signal()


class Job(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.events = Events()
        self.cancel = threading.Event()

    def run(self):
        try: self.events.result.emit(self.function(self.cancel, self.events.progress.emit))
        except Exception as error: self.events.error.emit(str(error))
        finally: self.events.finished.emit()


def import_images(root, sources, cancel, progress):
    project = Project(root, create=False)
    added, found, damaged, batch = 0, 0, [], []
    started = time.perf_counter()
    def paths():
        for source in sources:
            source = Path(source)
            if source.is_dir():
                for folder, _, files in os.walk(source):
                    if cancel.is_set(): return
                    for name in files:
                        if Path(name).suffix.lower() in FORMATS: yield Path(folder)/name
            else: yield source
    try:
        for path in paths():
            if cancel.is_set(): break
            found += 1
            try:
                if path.suffix.lower() not in FORMATS: raise ValueError('Unsupported image format')
                with Image.open(path) as im:
                    width, height = im.size
                    if im.getexif().get(274,1) in (5,6,7,8): width,height = height,width
                # PNG EXIF lookup may consume the file; verify needs a fresh reader.
                with Image.open(path) as im:
                    im.verify()
                batch.append((project.reference(path),width,height))
            except Exception as error:
                if len(damaged)<100: damaged.append(f'{path.name}: {error}')
            if len(batch)>=128:
                added += project.add_batch(batch); batch.clear()
            if found%32==0: progress(found, f'Inspected {found:,} images · {added+len(batch):,} imported')
        if batch: added += project.add_batch(batch)
        return {'added':added,'scanned':found,'errors':damaged,'cancelled':cancel.is_set(),'seconds':time.perf_counter()-started}
    finally: project.close()


PREVIEW_EDGE = 2560
DETAIL_MAX_PIXELS = 64_000_000


def to_qimage(image):
    # ARGB32_Premultiplied is QPainter's native format, so painting never converts per frame.
    image = image.convert('RGBA')
    return QImage(image.tobytes(), image.width, image.height, image.width*4,
                  QImage.Format_RGBA8888).convertToFormat(QImage.Format_ARGB32_Premultiplied)


def decode(path, edge=PREVIEW_EDGE):
    """Fast display preview; stored coordinates/dimensions remain full resolution."""
    with Image.open(path) as image:
        image.draft('RGB',(edge,edge))
        image = ImageOps.exif_transpose(image)
        image.thumbnail((edge,edge),Image.Resampling.LANCZOS)
        return to_qimage(image)


def decode_full(path, max_pixels=DETAIL_MAX_PIXELS):
    with Image.open(path) as image:
        if image.width*image.height > max_pixels:
            raise ValueError(f'{image.width:,} × {image.height:,} px exceeds the {max_pixels/1e6:.0f} MP detail limit')
        return to_qimage(ImageOps.exif_transpose(image))


class ImageLoader(QObject):
    """One background decoder with priorities: current image, then full-resolution detail, then prefetch."""
    ready = Signal(object, object)
    failed = Signal(object, str)
    detail_ready = Signal(object, object)
    detail_failed = Signal(object, str)

    def __init__(self, parent=None, budget=96*1024*1024):
        super().__init__(parent)
        self.pool = QThreadPool(self); self.pool.setMaxThreadCount(1)
        self.cache = OrderedDict(); self.bytes = 0; self.budget = budget
        self.active = None; self.pending = None; self.pending_detail = None; self.prefetching = []
        self.detail = None

    @staticmethod
    def key(path):
        return (str(path), Path(path).stat().st_mtime_ns)

    def request(self, token, path):
        try: key = self.key(path)
        except OSError as e: self.failed.emit(token,str(e)); return
        if key in self.cache:
            self.cache.move_to_end(key); self.ready.emit(token,self.cache[key]); return
        self.pending = (token,key); self._pump()

    def request_detail(self, token, path, max_pixels=DETAIL_MAX_PIXELS):
        try: key = self.key(path)
        except OSError as e: self.detail_failed.emit(token,str(e)); return
        if self.detail and self.detail[0] == key: self.detail_ready.emit(token,self.detail[1]); return
        self.detail = None
        self.pending_detail = (token,key,max_pixels); self._pump()

    def prefetch(self, paths):
        for path in paths:
            try: key = self.key(path)
            except OSError: continue
            if key not in self.cache and key not in self.prefetching: self.prefetching.append(key)
        self._pump()

    def stop(self):
        """Drop queued work and wait for the in-flight decode (decodes cannot be interrupted)."""
        self.pending = None; self.pending_detail = None; self.prefetching.clear()
        self.pool.waitForDone(5000)

    def _pump(self):
        if self.active: return
        if self.pending:
            (token,key), self.pending = self.pending, None
            if key in self.prefetching: self.prefetching.remove(key)
            self._start('preview', token, key, lambda: decode(key[0]))
        elif self.pending_detail:
            (token,key,limit), self.pending_detail = self.pending_detail, None
            self._start('detail', token, key, lambda: decode_full(key[0], limit))
        elif self.prefetching:
            key = self.prefetching.pop(0)
            if key in self.cache: self._pump(); return
            self._start('prefetch', None, key, lambda: decode(key[0]))

    def _start(self, kind, token, key, work):
        job = Job(lambda cancel,progress: (kind,token,key,work()))
        self.active = job; self.active_kind = kind; self.active_token = token
        job.events.result.connect(self._loaded)
        job.events.error.connect(self._error)
        job.events.finished.connect(self._finished)
        self.pool.start(job)

    def _store(self, key, image):
        size = image.sizeInBytes()
        while self.cache and self.bytes+size > self.budget:
            _, previous = self.cache.popitem(last=False); self.bytes -= previous.sizeInBytes()
        if size <= self.budget: self.cache[key] = image; self.bytes += size

    @Slot(object)
    def _loaded(self, payload):
        kind,token,key,image = payload
        if kind == 'detail':
            self.detail = (key,image); self.detail_ready.emit(token,image); return
        self._store(key,image)
        if kind == 'preview': self.ready.emit(token,image)

    @Slot(str)
    def _error(self, error):
        if self.active_kind == 'preview': self.failed.emit(self.active_token,error)
        elif self.active_kind == 'detail': self.detail_failed.emit(self.active_token,error)

    @Slot()
    def _finished(self):
        self.active = None
        self._pump()
