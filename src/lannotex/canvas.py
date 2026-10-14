"""Native canvas. Geometry lives in the document, never in disposable graphics items."""
from copy import deepcopy
import math
from PIL import Image
from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget
from .domain import Annotation, validate


MAX_PIXEL_SCALE = 64
GRID_FROM_SCALE = 12
MINIMAP = QSizeF(200, 140)


def build_lut(brightness=0, contrast=0, gamma=1.):
    """Display-only tone curve. brightness/contrast in -100..100, gamma 0.2..3. None = identity."""
    if brightness == 0 and contrast == 0 and gamma == 1: return None
    factor = 1 + contrast/100 if contrast <= 0 else 1 / (1 - min(contrast, 99)/100)
    lut = []
    for v in range(256):
        x = min(1., max(0., (v/255 - .5)*factor + .5 + brightness/200))
        lut.append(round(x ** (1/gamma) * 255))
    return lut


def apply_lut(image, lut):
    w, h = image.width(), image.height()
    pil = Image.frombuffer('RGBA', (w, h), bytes(image.constBits()), 'raw', 'BGRA', image.bytesPerLine(), 1)
    out = pil.point(lut*3 + list(range(256))).tobytes('raw', 'BGRA')
    return QImage(out, w, h, w*4, QImage.Format_ARGB32_Premultiplied).copy()


class Canvas(QWidget):
    edited = Signal(object)
    selected = Signal(object)
    zoomed = Signal(int)
    message = Signal(str)
    detail_wanted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(280, 200)
        self.setAccessibleName('Image annotation canvas')
        self.image = None
        self.annotations = []
        self.colors = {}
        self.label = ''
        self.mode = 'select'
        self.selection = None
        self.vertex = None
        self.opacity = .15
        self.zoom = 1.
        self.pan = QPointF()
        self.points = []
        self.drag = None
        self.preview = None
        self.redraw_id = None
        self.space = False
        self.empty_title = 'Your next dataset starts here'
        self.empty_detail = 'Create or open a project, then import your images.'
        self.detail = None
        self.source = None
        self.detail_requested = False
        self.show_minimap = True
        self.show_grid = True
        self.minimap_rect = QRectF()
        self.minimap_drag = False
        self.adjustments = (0, 0, 1.)
        self.lut = None
        self.adjusted = None

    def set_adjustments(self, brightness=0, contrast=0, gamma=1.):
        self.adjustments = (brightness, contrast, gamma)
        self.lut = build_lut(brightness, contrast, gamma)
        self.adjusted = None
        self.update()

    def set_image(self, image, source=None):
        """`image` is a display preview; `source` is the original (width, height) after EXIF rotation."""
        self.cancel()
        self.image = image
        self.detail = None
        self.adjusted = None
        self.detail_requested = False
        self.source = source or ((image.width(), image.height()) if image is not None else None)
        self.fit()

    def set_detail(self, image):
        self.detail = image
        self.update()

    def needs_detail(self):
        return self.image is not None and self.source is not None and self.source[0] > self.image.width()

    def source_scale(self):
        """Screen pixels per original image pixel (1.0 = 100%)."""
        if self.image is None or not self.source: return 1.
        return self.image_rect().width() / self.source[0]

    def base_scale(self):
        w, h = self.image.width(), self.image.height()
        return min(max(1, self.width()-64)/w, max(1, self.height()-64)/h)

    def set_zoom(self, zoom, anchor=None):
        if self.image is None: return
        top = MAX_PIXEL_SCALE * self.source[0] / (self.image.width() * self.base_scale())
        anchor = anchor if anchor is not None else QPointF(self.width()/2, self.height()/2)
        before = self.image_rect()
        u = (anchor.x()-before.x())/before.width(); v = (anchor.y()-before.y())/before.height()
        self.zoom = max(.1, min(max(1., top), zoom))
        after = self.image_rect()
        self.pan += QPointF(anchor.x()-(after.x()+u*after.width()), anchor.y()-(after.y()+v*after.height()))
        self.zoomed.emit(round(self.source_scale()*100))
        self.update()

    def zoom_by(self, factor, anchor=None): self.set_zoom(self.zoom*factor, anchor)

    def actual_pixels(self):
        if self.image is not None: self.set_zoom(self.source[0] / (self.image.width() * self.base_scale()))

    def center_on(self, nx, ny):
        r = self.image_rect()
        self.pan += QPointF(self.width()/2-(r.left()+nx*r.width()), self.height()/2-(r.top()+ny*r.height()))
        self.update()

    def toggle_minimap(self): self.show_minimap = not self.show_minimap; self.update()
    def toggle_grid(self): self.show_grid = not self.show_grid; self.update()

    def set_annotations(self, annotations):
        self.annotations = deepcopy(annotations)
        if not any(a.id == self.selection for a in annotations): self.select(None)
        self.update()

    def set_mode(self, mode):
        self.cancel()
        self.mode = mode
        self.setCursor(Qt.CrossCursor if mode in ('box', 'polygon') else Qt.ArrowCursor)
        self.setFocus()

    def select(self, ident):
        self.selection = ident
        self.vertex = None
        self.selected.emit(ident)
        self.update()

    def fit(self):
        self.zoom = 1.
        self.pan = QPointF()
        self.zoomed.emit(round(self.source_scale()*100))
        self.update()

    def image_rect(self):
        if self.image is None: return QRectF()
        w, h = self.image.width(), self.image.height()
        scale = min(max(1, self.width()-64)/w, max(1, self.height()-64)/h)*self.zoom
        return QRectF((self.width()-w*scale)/2+self.pan.x(), (self.height()-h*scale)/2+self.pan.y(), w*scale, h*scale)

    def screen(self, p):
        r = self.image_rect()
        return QPointF(r.left()+p[0]*r.width(), r.top()+p[1]*r.height())

    def normalized(self, p):
        r = self.image_rect()
        return [max(0., min(1., (p.x()-r.left())/max(1,r.width()))), max(0., min(1., (p.y()-r.top())/max(1,r.height())))]

    @staticmethod
    def vertices(a):
        if a.kind == 'polygon': return a.geometry
        if a.kind == 'box':
            x,y,r,b = a.geometry
            return [[x,y],[r,y],[r,b],[x,b]]
        return []

    def sized_font(self, points, weight=QFont.Normal):
        font = QFont(self.font())
        font.setPointSize(points)
        font.setWeight(weight)
        return font

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setRenderHint(QPainter.Antialiasing)
        if self.image is None:
            painter.setPen(self.palette().text().color())
            painter.setFont(self.sized_font(20, QFont.DemiBold))
            painter.drawText(self.rect().adjusted(24,-30,-24,-30), Qt.AlignCenter, self.empty_title)
            painter.setFont(self.sized_font(10))
            painter.drawText(self.rect().adjusted(24,50,-24,50), Qt.AlignCenter | Qt.TextWordWrap, self.empty_detail)
            return
        r = self.image_rect()
        scale = self.source_scale()
        preview_scale = self.image.width() / self.source[0]
        if self.detail is None and scale > preview_scale * 1.05 and self.needs_detail() and not self.detail_requested:
            self.detail_requested = True; self.detail_wanted.emit()
        use_detail = self.detail is not None and scale > preview_scale
        self.draw_visible(painter, r, self.detail if use_detail else self.image)
        painter.setClipRect(r)
        if self.show_grid and scale >= GRID_FROM_SCALE: self.draw_grid(painter, r, scale)
        shown = self.preview if self.preview is not None else self.annotations
        for n, a in enumerate(shown, 1):
            pts = self.vertices(a)
            if not pts: continue
            color = QColor(self.colors.get(a.label, '#38bfa7'))
            selected = a.id == self.selection
            painter.setPen(QPen(color, 2.4 if selected else 1.5))
            fill = QColor(color); fill.setAlphaF(self.opacity)
            painter.setBrush(fill)
            poly = QPolygonF([self.screen(p) for p in pts])
            painter.drawPolygon(poly)
            anchor = poly.boundingRect().topLeft()
            text = f'{n}  {a.label}'
            painter.setFont(self.sized_font(9, QFont.DemiBold))
            width = painter.fontMetrics().horizontalAdvance(text)+14
            badge = QRectF(anchor.x(), max(r.top(), anchor.y()-23), width, 22)
            painter.fillRect(badge, color)
            painter.setPen(QColor('#101820'))
            painter.drawText(badge, Qt.AlignCenter, text)
            if selected:
                for i, p in enumerate(poly):
                    painter.setPen(QPen(color, 1.5))
                    painter.setBrush(QColor('#f4f8fc') if i != self.vertex else QColor('#f4ba58'))
                    painter.drawRect(QRectF(p.x()-4,p.y()-4,8,8))
        painter.setClipping(False)
        if self.points:
            painter.setPen(QPen(QColor('#f4ba58'), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolyline(QPolygonF([self.screen(p) for p in self.points]))
            for p in self.points:
                painter.setBrush(QColor('#f4ba58')); painter.drawEllipse(self.screen(p), 3.5, 3.5)
        self.draw_minimap(painter, r)

    def draw_visible(self, painter, r, image):
        """Draw only the on-screen part of the image; cost tracks the viewport, not the image size."""
        visible = r.intersected(QRectF(self.rect()))
        if visible.isEmpty(): return
        sx, sy = image.width()/r.width(), image.height()/r.height()
        source = QRectF((visible.left()-r.left())*sx, (visible.top()-r.top())*sy, visible.width()*sx, visible.height()*sy)
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, r.width()/image.width() < 3)
        if self.lut is None:
            painter.drawImage(visible, image, source)
        else:
            # Tone-adjust only the on-screen pixels; whole-pixel bounds keep the crop aligned with the geometry.
            src = source.toAlignedRect().intersected(image.rect())
            key = (image.cacheKey(), src.x(), src.y(), src.width(), src.height(), self.adjustments)
            if self.adjusted is None or self.adjusted[0] != key:
                self.adjusted = (key, apply_lut(image.copy(src), self.lut))
            target = QRectF(r.left()+src.x()/sx, r.top()+src.y()/sy, src.width()/sx, src.height()/sy)
            painter.drawImage(target, self.adjusted[1])
        painter.restore()

    def draw_grid(self, painter, r, scale):
        visible = r.intersected(QRectF(self.rect()))
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(QPen(QColor(16, 16, 16, 120), 1))
        first_x = math.floor((visible.left()-r.left())/scale); last_x = math.ceil((visible.right()-r.left())/scale)
        first_y = math.floor((visible.top()-r.top())/scale); last_y = math.ceil((visible.bottom()-r.top())/scale)
        for i in range(first_x, last_x+1):
            x = r.left()+i*scale; painter.drawLine(QPointF(x, visible.top()), QPointF(x, visible.bottom()))
        for j in range(first_y, last_y+1):
            y = r.top()+j*scale; painter.drawLine(QPointF(visible.left(), y), QPointF(visible.right(), y))
        painter.restore()

    def draw_minimap(self, painter, r):
        self.minimap_rect = QRectF()
        if not self.show_minimap or QRectF(self.rect()).contains(r): return
        w, h = self.image.width(), self.image.height()
        k = min(MINIMAP.width()/w, MINIMAP.height()/h)
        box = QRectF(self.width()-w*k-14, self.height()-h*k-14, w*k, h*k)
        self.minimap_rect = box
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setOpacity(.92)
        painter.fillRect(box.adjusted(-3, -3, 3, 3), self.palette().window())
        painter.drawImage(box, self.image)
        painter.setOpacity(1)
        view = QRectF(self.rect()).intersected(r)
        viewport = QRectF(box.left()+(view.left()-r.left())/r.width()*box.width(), box.top()+(view.top()-r.top())/r.height()*box.height(),
                          view.width()/r.width()*box.width(), view.height()/r.height()*box.height())
        if viewport.width() < 8 or viewport.height() < 8:
            center = viewport.center(); viewport = QRectF(center.x()-4, center.y()-4, 8, 8)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 160), 3)); painter.drawRect(viewport)
        painter.setPen(QPen(QColor('#37b8a5'), 1.6)); painter.drawRect(viewport)
        painter.setPen(QPen(self.palette().mid().color(), 1)); painter.drawRect(box.adjusted(-3, -3, 3, 3))
        painter.restore()

    def minimap_jump(self, pos):
        box = self.minimap_rect
        self.center_on(min(1, max(0, (pos.x()-box.left())/box.width())), min(1, max(0, (pos.y()-box.top())/box.height())))

    def wheelEvent(self, event):
        if self.image is None: return
        self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1/1.15, event.position())

    def mousePressEvent(self, event):
        self.setFocus()
        if self.image is None: return
        if event.button() == Qt.LeftButton and self.minimap_rect.contains(event.position()):
            self.minimap_drag = True; self.minimap_jump(event.position()); return
        if event.button() == Qt.MiddleButton or (self.space and event.button() == Qt.LeftButton):
            self.drag = {'kind':'pan','start':event.position(),'pan':QPointF(self.pan)}
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() != Qt.LeftButton or not self.image_rect().contains(event.position()): return
        p = self.normalized(event.position())
        if self.mode in ('box','polygon'):
            if not self.label:
                self.message.emit('Add and select a label before drawing.'); return
            if self.mode == 'polygon':
                if len(self.points) >= 1000: self.message.emit('A polygon supports up to 1000 vertices.'); return
                self.points.append(p); self.update(); return
            self.drag = {'kind':'draw','start':p}
            return
        chosen = next((a for a in self.annotations if a.id == self.selection), None)
        if chosen:
            for i, vertex in enumerate(self.vertices(chosen)):
                q = self.screen(vertex)
                if math.hypot(q.x()-event.position().x(),q.y()-event.position().y()) < 10:
                    self.vertex = i
                    self.drag = {'kind':'vertex','start':p,'original':deepcopy(chosen),'vertex':i}
                    self.update(); return
        for a in reversed(self.annotations):
            if QPolygonF([self.screen(v) for v in self.vertices(a)]).containsPoint(event.position(), Qt.OddEvenFill):
                self.select(a.id)
                self.drag = {'kind':'move','start':p,'original':deepcopy(a)}
                return
        self.select(None)

    def mouseMoveEvent(self, event):
        if self.minimap_drag: self.minimap_jump(event.position()); return
        if not self.drag: return
        d = self.drag
        if d['kind'] == 'pan':
            self.pan = d['pan']+event.position()-d['start']; self.update(); return
        p = self.normalized(event.position())
        if d['kind'] == 'draw':
            x,y = d['start']
            a = Annotation(self.label, 'box', [min(x,p[0]),min(y,p[1]),max(x,p[0]),max(y,p[1])])
            if self.redraw_id: a.id = self.redraw_id
            self.preview = [b for b in self.annotations if b.id != a.id]+[a]
        else:
            a = deepcopy(d['original'])
            if d['kind'] == 'move':
                pts = self.vertices(a)
                dx = max(-min(v[0] for v in pts),min(1-max(v[0] for v in pts),p[0]-d['start'][0]))
                dy = max(-min(v[1] for v in pts),min(1-max(v[1] for v in pts),p[1]-d['start'][1]))
                if a.kind == 'box': a.geometry = [a.geometry[0]+dx,a.geometry[1]+dy,a.geometry[2]+dx,a.geometry[3]+dy]
                else: a.geometry = [[v[0]+dx,v[1]+dy] for v in pts]
            elif a.kind == 'polygon': a.geometry[d['vertex']] = p
            else:
                opposite = self.vertices(a)[(d['vertex']+2)%4]
                a.geometry = [min(p[0],opposite[0]),min(p[1],opposite[1]),max(p[0],opposite[0]),max(p[1],opposite[1])]
            self.preview = [a if b.id == a.id else b for b in self.annotations]
        self.update()

    def mouseReleaseEvent(self, event):
        if self.minimap_drag: self.minimap_drag = False; return
        if not self.drag: return
        kind = self.drag['kind']
        self.drag = None
        if kind == 'pan': self.setCursor(Qt.OpenHandCursor if self.space else Qt.ArrowCursor); return
        if self.preview is not None:
            errors = [error for a in self.preview for error in validate(a,set(self.colors))]
            if errors: self.message.emit(errors[0])
            else:
                if kind == 'draw': self.selection = self.preview[-1].id
                self.edited.emit(deepcopy(self.preview))
                self.selected.emit(self.selection)
                self.redraw_id = None
        self.preview = None
        self.update()

    def finish_polygon(self):
        if not self.points: return
        a = Annotation(self.label,'polygon',deepcopy(self.points))
        if self.redraw_id: a.id = self.redraw_id
        errors = validate(a, set(self.colors))
        if errors: self.message.emit(errors[0]); return
        self.selection = a.id
        self.edited.emit([b for b in self.annotations if b.id != a.id]+[a])
        self.selected.emit(a.id)
        self.points = []; self.redraw_id = None; self.update()

    def mouseDoubleClickEvent(self, event):
        if self.mode != 'select' or self.image is None: return
        a = next((deepcopy(x) for x in self.annotations if x.id == self.selection and x.kind == 'polygon'), None)
        if a is None: return
        pos = event.position(); best = None
        for i, (p,q) in enumerate(zip(a.geometry,a.geometry[1:]+a.geometry[:1])):
            u,v = self.screen(p),self.screen(q)
            dx,dy = v.x()-u.x(),v.y()-u.y()
            t = max(0,min(1,((pos.x()-u.x())*dx+(pos.y()-u.y())*dy)/max(1e-8,dx*dx+dy*dy)))
            distance = math.hypot(pos.x()-u.x()-t*dx,pos.y()-u.y()-t*dy)
            if best is None or distance < best[0]: best = (distance,i,[p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])])
        if best and best[0] < 12:
            a.geometry.insert(best[1]+1,best[2])
            if not validate(a,set(self.colors)): self.edited.emit([a if b.id==a.id else b for b in self.annotations])
        self.drag = None

    def delete_vertex(self):
        a = next((deepcopy(x) for x in self.annotations if x.id == self.selection and x.kind=='polygon'), None)
        if a is None or self.vertex is None: return
        if len(a.geometry) <= 3: self.message.emit('A polygon must retain at least three vertices.'); return
        a.geometry.pop(self.vertex)
        errors = validate(a,set(self.colors))
        if errors: self.message.emit(errors[0]); return
        self.vertex = None
        self.edited.emit([a if b.id==a.id else b for b in self.annotations])

    def redraw(self):
        a = next((x for x in self.annotations if x.id == self.selection and x.kind != 'classification'), None)
        if a:
            self.set_mode(a.kind); self.redraw_id = a.id; self.label = a.label
            self.message.emit('Draw the replacement. Escape keeps the original annotation.')

    def cancel(self):
        self.points = []; self.drag = None; self.preview = None; self.redraw_id = None
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.space = True; self.setCursor(Qt.OpenHandCursor); event.accept(); return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.space = False; self.setCursor(Qt.ArrowCursor); event.accept(); return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self.space = False
        if self.drag: self.cancel()
        super().focusOutEvent(event)
