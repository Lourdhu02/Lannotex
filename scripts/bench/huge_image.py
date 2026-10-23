"""Opening, panning and zooming an image far larger than memory.

Run:  python scripts/bench/huge_image.py --pixels 30000 --cache <dir>
Generates a synthetic TIFF once and reuses it. Reports time to first paint, the one-off
pyramid build, and steady-state pan/zoom frame times with peak process memory.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from PIL import Image  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lannotex.canvas import Canvas  # noqa: E402
from lannotex.tiles import Pyramid  # noqa: E402
from lannotex.workers import decode  # noqa: E402

Image.MAX_IMAGE_PIXELS = None


def peak_memory_mb() -> float:
    try:
        import psutil
    except ImportError:
        return 0.0
    info = psutil.Process().memory_info()
    return getattr(info, "peak_wset", info.rss) / 1e6


def current_memory_mb() -> float:
    try:
        import psutil
    except ImportError:
        return 0.0
    return psutil.Process().memory_info().rss / 1e6


def make_image(path: Path, pixels: int) -> None:
    if path.exists():
        return
    print(f"generating {pixels}x{pixels} ({pixels * pixels / 1e6:.0f} MP) TIFF, this takes a while…", flush=True)
    image = Image.new("RGB", (pixels, pixels))
    band_height = 1024
    for y in range(0, pixels, band_height):
        height = min(band_height, pixels - y)
        shade = (y * 255 // pixels, 128, 255 - y * 255 // pixels)
        band = Image.new("RGB", (pixels, height), shade)
        for x in range(0, pixels, 2048):
            band.paste(Image.new("RGB", (64, height), (255, 255, 0)), (x, 0))
        image.paste(band, (0, y))
    image.save(path, compression="tiff_deflate")
    image.close()


def timed(fn, repeats: int) -> dict:
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    index = max(0, int(len(samples) * 0.95) - 1)
    return {"p50": round(statistics.median(samples), 2), "p95": round(samples[index], 2)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pixels", type=int, default=30000)
    parser.add_argument("--cache", default=None)
    parser.add_argument("--json", default=None)
    parser.add_argument("--keep", action="store_true", help="reuse an existing pyramid cache")
    args = parser.parse_args(argv)

    scratch = Path(args.cache or Path(os.environ.get("TEMP", "/tmp")) / "lannotex-huge")
    scratch.mkdir(parents=True, exist_ok=True)
    source = scratch / f"huge_{args.pixels}.tif"
    make_image(source, args.pixels)
    size_mb = source.stat().st_size / 1e6

    cache = scratch / "pyramids"
    pyramid = Pyramid(source, args.pixels, args.pixels, cache)
    if not args.keep:
        import shutil

        shutil.rmtree(pyramid.folder, ignore_errors=True)
        pyramid = Pyramid(source, args.pixels, args.pixels, cache)

    results: dict = {"pixels": args.pixels, "megapixels": round(args.pixels**2 / 1e6), "file_mb": round(size_mb)}
    app = QApplication.instance() or QApplication([])
    canvas = Canvas()
    canvas.resize(1600, 1000)
    canvas.show()
    app.processEvents()

    def paint():
        canvas.grab()  # renders through paintEvent even when the window is not on screen

    start = time.perf_counter()
    preview = decode(source)
    canvas.set_image(preview, (args.pixels, args.pixels))
    paint()
    results["cold_first_paint_ms"] = round((time.perf_counter() - start) * 1000, 1)
    results["after_first_paint_mb"] = round(current_memory_mb())

    cancel = threading.Event()
    start = time.perf_counter()
    built = pyramid.build(cancel, lambda value, message: None)
    results["build_ms"] = round((time.perf_counter() - start) * 1000, 1)
    results["levels"] = built["levels"]
    results["tiles"] = built.get("tiles", 0)
    results["cache_mb"] = round(sum(f.stat().st_size for f in pyramid.folder.rglob("*.jpg")) / 1e6)

    canvas.set_pyramid(pyramid)
    canvas.actual_pixels()
    paint()
    results["tiles_drawn"] = canvas.draw_tiles_count

    steps = iter(range(10_000))

    def pan():
        canvas.center_on(0.3 + (next(steps) % 40) * 0.01, 0.4)
        paint()

    results["pan_at_100pct"] = timed(pan, 40)

    def zoom_cycle():
        canvas.set_zoom(canvas.zoom * 1.4)
        paint()
        canvas.set_zoom(canvas.zoom / 1.4)
        paint()

    results["zoom"] = timed(zoom_cycle, 20)

    # Reopening the image: the pyramid on disk replaces decoding the source entirely.
    reopened = Pyramid(source, args.pixels, args.pixels, cache)
    assert reopened.complete(), "pyramid should already be on disk"
    canvas.set_image(None)
    start = time.perf_counter()
    canvas.set_image(reopened.compose(reopened.preview_level()), (args.pixels, args.pixels))
    canvas.set_pyramid(reopened)
    paint()
    results["warm_first_paint_ms"] = round((time.perf_counter() - start) * 1000, 1)
    results["peak_mb"] = round(peak_memory_mb())
    results["final_mb"] = round(current_memory_mb())

    print(json.dumps(results, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
