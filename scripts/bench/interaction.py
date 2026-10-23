"""Interaction latency on a dense image: edit, undo, hit-test and save.

Run:  python scripts/bench/interaction.py [--shapes 2000] [--json out.json]
CI gate: p95 must stay under EDIT_BUDGET_MS for edits and SAVE_BUDGET_MS for saves.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lannotex.domain import Annotation, Document, validate_all  # noqa: E402
from lannotex.storage import Project  # noqa: E402

# Budgets cover the interactive path: what happens between the user moving the mouse and the
# UI being ready again. A full save is durable I/O proportional to the dataset, so it is
# reported rather than gated; see docs/PERFORMANCE.md.
EDIT_BUDGET_MS = 16.0
SAVE_BUDGET_MS = 50.0
GATED = {
    "move_shape": EDIT_BUDGET_MS,
    "drag_vertex": EDIT_BUDGET_MS,
    "undo": EDIT_BUDGET_MS,
    "hit_test": EDIT_BUDGET_MS,
    "save_draft": SAVE_BUDGET_MS,
}
REPORTED = ("paint", "save_annotations", "validate_all", "load_annotations")


def build_shapes(count: int, seed: int = 7) -> list[Annotation]:
    """Mixed boxes and 50-500 vertex convex polygons, spread over the image."""
    rng = random.Random(seed)
    shapes: list[Annotation] = []
    for i in range(count):
        label = f"class{i % 8}"
        cx, cy = rng.uniform(0.08, 0.92), rng.uniform(0.08, 0.92)
        if i % 3 == 0:
            w, h = rng.uniform(0.01, 0.05), rng.uniform(0.01, 0.05)
            geometry = [max(0.0, cx - w), max(0.0, cy - h), min(1.0, cx + w), min(1.0, cy + h)]
            shapes.append(Annotation(label, "box", geometry))
            continue
        sides = rng.randint(50, 500)
        radius = rng.uniform(0.01, 0.06)
        points = []
        for k in range(sides):
            t = 2 * math.pi * k / sides
            points.append(
                [min(1.0, max(0.0, cx + radius * math.cos(t))), min(1.0, max(0.0, cy + radius * math.sin(t)))]
            )
        deduped = []
        for p in points:
            if not deduped or p != deduped[-1]:
                deduped.append(p)
        if len(deduped) >= 3:
            shapes.append(Annotation(label, "polygon", deduped))
    return shapes


def timed(fn, repeats: int) -> dict:
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return {
        "p50": round(statistics.median(samples), 3),
        "p95": round(samples[max(0, math.ceil(len(samples) * 0.95) - 1)], 3),
        "max": round(samples[-1], 3),
        "runs": repeats,
    }


def measure_canvas(annotations) -> dict:
    """Hit-testing and painting go through the same caches the real canvas uses."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication
        from lannotex.canvas import Canvas
    except ImportError:
        return {}

    app = QApplication.instance() or QApplication([])
    canvas = Canvas()
    canvas.resize(1600, 1000)
    canvas.colors = {a.label: "#37b8a5" for a in annotations}
    canvas.set_image(QImage(2560, 1600, QImage.Format_ARGB32_Premultiplied), (4000, 2500))
    canvas.set_annotations(annotations)
    rect = canvas.image_rect()
    spots = [(0.13, 0.17), (0.42, 0.61), (0.78, 0.35), (0.5, 0.5), (0.91, 0.88)]
    index = iter(range(10_000))

    def hit_test():
        nx, ny = spots[next(index) % len(spots)]
        for a in reversed(canvas.annotations):
            box = canvas.bounds(a)
            if box is None or not (box[0] <= nx <= box[2] and box[1] <= ny <= box[3]):
                continue
            canvas.screen_polygon(a, rect).containsPoint(canvas.screen([nx, ny]), Qt.OddEvenFill)

    hit_test()
    out = {"hit_test": timed(hit_test, 40)}
    out["paint"] = timed(canvas.repaint, 10)
    app.processEvents()
    return out


def measure(count: int) -> dict:
    shapes = build_shapes(count)
    labels = {a.label for a in shapes}
    results: dict[str, dict] = {"shapes": len(shapes)}

    results["validate_all"] = timed(lambda: validate_all(shapes, labels), 3)

    document = Document(shapes)
    moving = len(document.annotations) - 1
    step = iter(range(1, 10_000))

    def move_shape():
        nudged = list(document.annotations)
        target = Annotation.from_dict(nudged[moving].to_dict())
        offset = next(step) * 1e-5
        if target.kind == "box":
            target.geometry = [min(1.0, v + offset) for v in target.geometry]
        else:
            target.geometry = [[min(1.0, x + offset), y] for x, y in target.geometry]
        nudged[moving] = target
        document.change(nudged)

    results["move_shape"] = timed(move_shape, 30)

    def drag_vertex():
        nudged = list(document.annotations)
        target = Annotation.from_dict(nudged[moving].to_dict())
        if target.kind == "polygon":
            x, y = target.geometry[0]
            target.geometry[0] = [min(1.0, x + next(step) * 1e-5), y]
        nudged[moving] = target
        document.change(nudged)

    results["drag_vertex"] = timed(drag_vertex, 30)
    results["undo"] = timed(lambda: document.undo() or document.redo(), 30)

    results.update(measure_canvas(document.annotations))

    root = Path(tempfile.mkdtemp(prefix="lannotex-bench-")) / "project"
    project = Project(root)
    for name in sorted(labels):
        project.add_label(name)
    image = project.add_image(root / "bench.png", 4000, 3000)
    project.save_annotations(image, shapes)

    def save_changed():
        move_shape()
        project.save_annotations(image, document.annotations)

    results["save_annotations"] = timed(save_changed, 10)
    results["save_draft"] = timed(
        lambda: project.save_draft(image, document.annotations, history=document.history_json()), 20
    )
    results["load_annotations"] = timed(lambda: project.load_annotations(image), 10)
    project.close()
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--shapes",
        type=int,
        default=600,
        help="600 is the gated dense-image size; 2000 is the stress run in docs/PERFORMANCE.md",
    )
    parser.add_argument("--json", help="write the raw measurements here")
    parser.add_argument("--check", action="store_true", help="exit non-zero if a budget is exceeded")
    args = parser.parse_args(argv)

    results = measure(args.shapes)
    results["machine"] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
    }

    print(f"{'operation':<20}{'p50 ms':>10}{'p95 ms':>10}{'budget':>10}")
    failures = []
    for name in list(GATED) + list(REPORTED):
        if name not in results:
            continue
        budget = GATED.get(name)
        row = results[name]
        flag = ""
        if budget is not None and row["p95"] > budget:
            flag = "  OVER"
            failures.append(f"{name} p95 {row['p95']} ms exceeds {budget} ms")
        print(f"{name:<20}{row['p50']:>10}{row['p95']:>10}{(budget or '-'):>10}{flag}")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
    if failures and args.check:
        print("\nFAILED:", *failures, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
