"""Annotation invariants and reversible document changes; no Qt or file I/O."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import asdict, dataclass, field
import math
import uuid


@dataclass
class Annotation:
    label: str
    kind: str
    geometry: list = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(data['label'], data['kind'], deepcopy(data.get('geometry', [])), data['id'])


def finite_unit(n):
    return isinstance(n, (float, int)) and not isinstance(n, bool) and math.isfinite(n) and 0 <= n <= 1


def box_valid(box):
    return (isinstance(box, list) and len(box) == 4 and all(finite_unit(n) for n in box)
            and box[2] - box[0] > 1e-8 and box[3] - box[1] > 1e-8)


def polygon_area(points):
    return abs(sum(a[0]*b[1] - b[0]*a[1] for a, b in zip(points, points[1:]+points[:1]))) / 2


def polygon_self_intersects(points):
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])

    def on(a, b, c):
        return (abs(cross(a, b, c)) < 1e-12 and min(a[0], b[0])-1e-12 <= c[0] <= max(a[0], b[0])+1e-12
                and min(a[1], b[1])-1e-12 <= c[1] <= max(a[1], b[1])+1e-12)

    n = len(points)
    for i in range(n):
        a, b = points[i], points[(i+1) % n]
        for j in range(i+1, n):
            if (i+1) % n == j or (j+1) % n == i: continue
            c, d = points[j], points[(j+1) % n]
            if (cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0
                    or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b)):
                return True
    return False


def validate(a, labels):
    errors = []
    if not isinstance(a.id, str) or not a.id.strip(): errors.append('Missing annotation ID')
    if a.label not in labels: errors.append(f'Unknown label: {a.label}')
    if a.kind not in ('box', 'polygon', 'classification'): errors.append('Unknown annotation type')
    if a.kind == 'box' and not box_valid(a.geometry): errors.append('Box must have positive size inside the image')
    if a.kind == 'classification' and a.geometry: errors.append('Classification cannot contain geometry')
    if a.kind == 'polygon':
        pts = a.geometry
        if not isinstance(pts, list) or not 3 <= len(pts) <= 1000:
            errors.append('Polygon needs 3–1000 vertices')
        elif any(not isinstance(p, list) or len(p) != 2 or not all(finite_unit(x) for x in p) for p in pts):
            errors.append('Polygon vertices must be inside the image')
        elif len({tuple(p) for p in pts}) != len(pts) or polygon_area(pts) < 1e-10:
            errors.append('Polygon has duplicate vertices or zero area')
        elif polygon_self_intersects(pts): errors.append('Polygon edges intersect')
    return errors


def validate_all(annotations, labels, negative=False):
    errors, seen, classes = [], set(), set()
    for a in annotations:
        errors.extend(validate(a, labels))
        if a.id in seen: errors.append(f'Duplicate annotation ID: {a.id}')
        seen.add(a.id)
        if a.kind == 'classification':
            if a.label in classes: errors.append(f'Duplicate class: {a.label}')
            classes.add(a.label)
    if negative and annotations: errors.append('No-target images cannot contain annotations')
    return errors


class Document:
    """One active image. History is bounded; persisted drafts survive navigation."""
    def __init__(self, annotations=(), negative=False):
        self.annotations = deepcopy(list(annotations))
        self.negative = negative
        self.undo_stack = []
        self.redo_stack = []

    def snapshot(self):
        return deepcopy((self.annotations, self.negative))

    def change(self, annotations, negative=False):
        next_state = deepcopy((list(annotations), negative))
        if self.snapshot() == next_state: return False
        self.undo_stack.append(self.snapshot())
        self.undo_stack = self.undo_stack[-100:]
        self.redo_stack.clear()
        self.annotations, self.negative = next_state
        return True

    def undo(self):
        if not self.undo_stack: return False
        self.redo_stack.append(self.snapshot())
        self.annotations, self.negative = self.undo_stack.pop()
        return True

    def redo(self):
        if not self.redo_stack: return False
        self.undo_stack.append(self.snapshot())
        self.annotations, self.negative = self.redo_stack.pop()
        return True
