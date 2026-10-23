"""Annotation invariants and reversible document changes; no Qt or file I/O."""

from __future__ import annotations

import heapq
import json
import math
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

KINDS = ("box", "polygon", "classification")
MAX_POLYGON_VERTICES = 1000
HISTORY_LIMIT = 100
_EPS = 1e-12


@dataclass
class Annotation:
    label: str
    kind: str
    geometry: list = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {"label": self.label, "kind": self.kind, "geometry": copy_geometry(self.geometry), "id": self.id}

    def copy(self) -> "Annotation":
        return Annotation(self.label, self.kind, copy_geometry(self.geometry), self.id)

    @classmethod
    def from_dict(cls, data: dict) -> "Annotation":
        return cls(data["label"], data["kind"], copy_geometry(data.get("geometry", [])), data["id"])


def copy_geometry(geometry: Any) -> list:
    """Copy box floats or polygon vertices without deepcopy's memo bookkeeping."""
    if not isinstance(geometry, list):
        return geometry
    return [list(p) if type(p) is list else p for p in geometry]


def finite_unit(n: Any) -> bool:
    return isinstance(n, (float, int)) and not isinstance(n, bool) and math.isfinite(n) and 0 <= n <= 1


def box_valid(box: Any) -> bool:
    return (
        isinstance(box, list)
        and len(box) == 4
        and all(finite_unit(n) for n in box)
        and box[2] - box[0] > 1e-8
        and box[3] - box[1] > 1e-8
    )


def polygon_area(points: Sequence[Sequence[float]]) -> float:
    pairs = zip(points, list(points[1:]) + list(points[:1]))
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in pairs)) / 2


def _cross(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on(a, b, c) -> bool:
    return (
        abs(_cross(a, b, c)) < _EPS
        and min(a[0], b[0]) - _EPS <= c[0] <= max(a[0], b[0]) + _EPS
        and min(a[1], b[1]) - _EPS <= c[1] <= max(a[1], b[1]) + _EPS
    )


def _edges_touch(a, b, c, d) -> bool:
    """True when segments a-b and c-d properly cross or merely graze each other."""
    return (
        _cross(a, b, c) * _cross(a, b, d) < 0
        and _cross(c, d, a) * _cross(c, d, b) < 0
        or _on(a, b, c)
        or _on(a, b, d)
        or _on(c, d, a)
        or _on(c, d, b)
    )


def polygon_self_intersects_pairwise(points: Sequence[Sequence[float]]) -> bool:
    """Reference O(n²) implementation. Kept as the oracle the fast path is tested against."""
    n = len(points)
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        for j in range(i + 1, n):
            if (i + 1) % n == j or (j + 1) % n == i:
                continue
            c, d = points[j], points[(j + 1) % n]
            if _edges_touch(a, b, c, d):
                return True
    return False


def polygon_self_intersects(points: Sequence[Sequence[float]]) -> bool:
    """Sweep the x axis, comparing only edges whose x ranges overlap.

    Two segments can intersect only if their x intervals overlap, so every candidate pair is
    still examined with the exact predicate above; the sweep just skips the pairs that cannot
    touch. O(n log n + k) for k overlapping pairs instead of O(n²).
    """
    n = len(points)
    if n < 4:
        return False
    spans = []
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        spans.append((min(a[0], b[0]), max(a[0], b[0]), i))
    spans.sort()
    active: list[tuple[float, int]] = []
    for lo, hi, i in spans:
        while active and active[0][0] < lo - _EPS:
            heapq.heappop(active)
        a, b = points[i], points[(i + 1) % n]
        for _, j in active:
            if (i + 1) % n == j or (j + 1) % n == i:
                continue
            if _edges_touch(a, b, points[j], points[(j + 1) % n]):
                return True
        heapq.heappush(active, (hi, i))
    return False


def validate(a: Annotation, labels: Iterable[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(a.id, str) or not a.id.strip():
        errors.append("Missing annotation ID")
    if a.label not in labels:
        errors.append(f"Unknown label: {a.label}")
    if a.kind not in KINDS:
        errors.append("Unknown annotation type")
    if a.kind == "box" and not box_valid(a.geometry):
        errors.append("Box must have positive size inside the image")
    if a.kind == "classification" and a.geometry:
        errors.append("Classification cannot contain geometry")
    if a.kind == "polygon":
        pts = a.geometry
        if not isinstance(pts, list) or not 3 <= len(pts) <= MAX_POLYGON_VERTICES:
            errors.append(f"Polygon needs 3–{MAX_POLYGON_VERTICES} vertices")
        elif any(not isinstance(p, list) or len(p) != 2 or not all(finite_unit(x) for x in p) for p in pts):
            errors.append("Polygon vertices must be inside the image")
        elif len({tuple(p) for p in pts}) != len(pts) or polygon_area(pts) < 1e-10:
            errors.append("Polygon has duplicate vertices or zero area")
        elif polygon_self_intersects(pts):
            errors.append("Polygon edges intersect")
    return errors


class ValidationCache:
    """Memoizes validate() per annotation object.

    Editing never mutates an annotation in place — the canvas and the importers build a new
    Annotation for the shape that changed and pass the untouched ones straight through — so
    object identity is a sound key. A strong reference is held so an id cannot be reused by a
    later object, and the vertex count is re-checked to catch in-place list edits.
    """

    def __init__(self, limit: int = 4096) -> None:
        self._entries: OrderedDict[int, tuple[Annotation, int, list[str]]] = OrderedDict()
        self._labels: frozenset[str] | None = None
        self._limit = limit

    def clear(self) -> None:
        self._entries.clear()
        self._labels = None

    def validate(self, a: Annotation, labels: Iterable[str]) -> list[str]:
        known = labels if isinstance(labels, frozenset) else frozenset(labels)
        if known != self._labels:
            self._entries.clear()
            self._labels = known
        key = id(a)
        hit = self._entries.get(key)
        if hit is not None and hit[0] is a and hit[1] == len(a.geometry):
            self._entries.move_to_end(key)
            return hit[2]
        errors = validate(a, known)
        self._entries[key] = (a, len(a.geometry), errors)
        self._entries.move_to_end(key)
        while len(self._entries) > self._limit:
            self._entries.popitem(last=False)
        return errors


class JsonCache:
    """Caches each annotation's compact JSON by object identity, on the same terms as ValidationCache."""

    def __init__(self, limit: int = 4096) -> None:
        self._entries: OrderedDict[int, tuple[Annotation, int, str]] = OrderedDict()
        self._limit = limit

    def clear(self) -> None:
        self._entries.clear()

    def dumps(self, a: Annotation) -> str:
        key = id(a)
        hit = self._entries.get(key)
        if hit is not None and hit[0] is a and hit[1] == len(a.geometry):
            self._entries.move_to_end(key)
            return hit[2]
        # json.dumps only reads the geometry, so serialize the live lists instead of a copy.
        text = json.dumps(
            {"label": a.label, "kind": a.kind, "geometry": a.geometry, "id": a.id},
            separators=(",", ":"),
        )
        self._entries[key] = (a, len(a.geometry), text)
        self._entries.move_to_end(key)
        while len(self._entries) > self._limit:
            self._entries.popitem(last=False)
        return text


_CACHE = ValidationCache()
_JSON = JsonCache()


def validate_cached(a: Annotation, labels: Iterable[str]) -> list[str]:
    """validate() memoized per annotation object; safe because edits build new objects."""
    return _CACHE.validate(a, labels)


def annotation_json(a: Annotation) -> str:
    """Compact JSON for one annotation, memoized per object."""
    return _JSON.dumps(a)


def validate_all(
    annotations: Sequence[Annotation],
    labels: Iterable[str],
    negative: bool = False,
    cache: ValidationCache | None = _CACHE,
) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    classes: set[str] = set()
    check = cache.validate if cache is not None else validate
    for a in annotations:
        errors.extend(check(a, labels))
        if a.id in seen:
            errors.append(f"Duplicate annotation ID: {a.id}")
        seen.add(a.id)
        if a.kind == "classification":
            if a.label in classes:
                errors.append(f"Duplicate class: {a.label}")
            classes.add(a.label)
    if negative and annotations:
        errors.append("No-target images cannot contain annotations")
    return errors


@dataclass
class Edit:
    """One reversible document change, stored as a delta rather than a full snapshot."""

    added: list[Annotation] = field(default_factory=list)
    removed: list[Annotation] = field(default_factory=list)
    updated: list[tuple[Annotation, Annotation]] = field(default_factory=list)
    order_before: list[str] = field(default_factory=list)
    order_after: list[str] = field(default_factory=list)
    negative_before: bool = False
    negative_after: bool = False
    _json: str | None = field(default=None, compare=False, repr=False)

    def json(self) -> str:
        """An edit never changes once recorded, so serialize it at most once."""
        if self._json is None:
            self._json = json.dumps(self.to_dict(), separators=(",", ":"))
        return self._json

    def empty(self) -> bool:
        return (
            not self.added
            and not self.removed
            and not self.updated
            and self.order_before == self.order_after
            and self.negative_before == self.negative_after
        )

    def to_dict(self) -> dict:
        return {
            "added": [a.to_dict() for a in self.added],
            "removed": [a.to_dict() for a in self.removed],
            "updated": [[b.to_dict(), a.to_dict()] for b, a in self.updated],
            "order_before": self.order_before,
            "order_after": self.order_after,
            "negative_before": self.negative_before,
            "negative_after": self.negative_after,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Edit":
        return cls(
            added=[Annotation.from_dict(a) for a in data.get("added", ())],
            removed=[Annotation.from_dict(a) for a in data.get("removed", ())],
            updated=[(Annotation.from_dict(b), Annotation.from_dict(a)) for b, a in data.get("updated", ())],
            order_before=list(data.get("order_before", ())),
            order_after=list(data.get("order_after", ())),
            negative_before=bool(data.get("negative_before", False)),
            negative_after=bool(data.get("negative_after", False)),
        )


class Document:
    """One active image. History stores deltas, so an edit costs the shapes it touched."""

    def __init__(self, annotations: Iterable[Annotation] = (), negative: bool = False) -> None:
        self.annotations: list[Annotation] = [a.copy() for a in annotations]
        self.negative = negative
        self.undo_stack: list[Edit] = []
        self.redo_stack: list[Edit] = []

    def snapshot(self) -> tuple[list[Annotation], bool]:
        return [a.copy() for a in self.annotations], self.negative

    def _diff(self, annotations: Sequence[Annotation], negative: bool) -> Edit:
        before = {a.id: a for a in self.annotations}
        edit = Edit(
            order_before=[a.id for a in self.annotations],
            order_after=[a.id for a in annotations],
            negative_before=self.negative,
            negative_after=negative,
        )
        for a in annotations:
            previous = before.pop(a.id, None)
            if previous is None:
                edit.added.append(a.copy())
            elif previous is not a and previous != a:
                edit.updated.append((previous.copy(), a.copy()))
        edit.removed.extend(a.copy() for a in before.values())
        return edit

    def change(self, annotations: Sequence[Annotation], negative: bool = False) -> bool:
        edit = self._diff(annotations, negative)
        if edit.empty():
            return False
        self.undo_stack.append(edit)
        del self.undo_stack[:-HISTORY_LIMIT]
        self.redo_stack.clear()
        self.annotations = list(annotations)
        self.negative = negative
        return True

    def _apply(self, edit: Edit, forward: bool) -> None:
        current = {a.id: a for a in self.annotations}
        for a in edit.added if forward else edit.removed:
            current[a.id] = a.copy()
        for a in edit.removed if forward else edit.added:
            current.pop(a.id, None)
        for before, after in edit.updated:
            replacement = after if forward else before
            current[replacement.id] = replacement.copy()
        order = edit.order_after if forward else edit.order_before
        self.annotations = [current[i] for i in order if i in current]
        self.negative = edit.negative_after if forward else edit.negative_before

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        edit = self.undo_stack.pop()
        self._apply(edit, forward=False)
        self.redo_stack.append(edit)
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        edit = self.redo_stack.pop()
        self._apply(edit, forward=True)
        self.undo_stack.append(edit)
        return True

    def history_state(self) -> dict:
        return {
            "undo": [e.to_dict() for e in self.undo_stack],
            "redo": [e.to_dict() for e in self.redo_stack],
        }

    def history_json(self) -> str:
        """Pre-serialized history for the draft row; reuses each edit's memoized JSON."""
        undo = ",".join(e.json() for e in self.undo_stack)
        redo = ",".join(e.json() for e in self.redo_stack)
        return '{"undo":[' + undo + '],"redo":[' + redo + "]}"

    def restore_history(self, state: dict | None) -> None:
        if not state:
            return
        try:
            self.undo_stack = [Edit.from_dict(e) for e in state.get("undo", ())][-HISTORY_LIMIT:]
            self.redo_stack = [Edit.from_dict(e) for e in state.get("redo", ())][-HISTORY_LIMIT:]
        except (KeyError, TypeError, ValueError):
            self.undo_stack = []
            self.redo_stack = []
