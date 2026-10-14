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


def decode(path):
    # Display preview is capped; stored coordinates/dimensions remain full resolution.
    with Image.open(path) as image:
        image.draft('RGB',(2560,2560))
        image = ImageOps.exif_transpose(image)
        image.thumbnail((2560,2560),Image.Resampling.LANCZOS)
        image = image.convert('RGBA')
        data = image.tobytes()
        return QImage(data,image.width,image.height,image.width*4,QImage.Format_RGBA8888).copy()


class ImageLoader(QObject):
    ready = Signal(object, object)
    failed = Signal(object, str)

    def __init__(self, parent=None, budget=96*1024*1024):
        super().__init__(parent)
        self.pool = QThreadPool(self); self.pool.setMaxThreadCount(1)
        self.cache = OrderedDict(); self.bytes = 0; self.budget = budget
        self.active = None; self.pending = None

    def request(self, token, path):
        path = str(path)
        try: key = (path, Path(path).stat().st_mtime_ns)
        except OSError as e: self.failed.emit(token,str(e)); return
        if key in self.cache:
            self.cache.move_to_end(key); self.ready.emit(token,self.cache[key]); return
        if self.active:
            self.pending = (token,path); return
        job = Job(lambda cancel,progress: (token,key,decode(path)))
        self.active = job
        job.events.result.connect(self._loaded)
        job.events.error.connect(self._error)
        job.events.finished.connect(self._finished)
        self.active_token = token
        self.pool.start(job)

    @Slot(object)
    def _loaded(self, payload):
        token,key,image = payload
        size = image.sizeInBytes()
        while self.cache and self.bytes+size > self.budget:
            _, previous = self.cache.popitem(last=False); self.bytes -= previous.sizeInBytes()
        if size <= self.budget: self.cache[key] = image; self.bytes += size
        self.ready.emit(token,image)

    @Slot(str)
    def _error(self, error): self.failed.emit(self.active_token,error)

    @Slot()
    def _finished(self):
        self.active = None
        if self.pending:
            token,path = self.pending; self.pending = None; self.request(token,path)
