"""Tile pyramids: levels, building, reuse and bounded caches."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from lannotex.tiles import TILE, Pyramid, TileCache, levels_for, prune, pyramid_key


@pytest.fixture(scope="module")
def qt():
    return QApplication.instance() or QApplication([])


def source_image(tmp_path, width, height, name="big.png"):
    path = tmp_path / name
    Image.new("RGB", (width, height), "#4080c0").save(path)
    return path


def test_levels_cover_down_to_a_single_tile():
    assert levels_for(TILE, TILE) == 1
    assert levels_for(TILE * 2, TILE) == 2
    assert levels_for(2200, 1100) == 4
    assert levels_for(30000, 30000) == 7


def test_build_writes_every_level_and_is_resumable(tmp_path, qt):
    path = source_image(tmp_path, 2200, 1100)
    pyramid = Pyramid(path, 2200, 1100, tmp_path / "cache")
    assert pyramid.levels == 4
    assert pyramid.level_size(0) == (2200, 1100)
    assert pyramid.level_size(1) == (1100, 550)
    assert pyramid.grid(0) == (5, 3)
    assert not pyramid.complete()

    built = pyramid.build(threading.Event(), lambda value, message: None)
    assert pyramid.complete() and built["tiles"] > 0
    assert pyramid.tile_path(0, 0, 0).is_file()
    assert pyramid.tile_path(0, 4, 2).is_file()

    again = Pyramid(path, 2200, 1100, tmp_path / "cache")
    assert again.complete()
    assert again.build(threading.Event(), lambda value, message: None)["skipped"]


def test_build_can_be_cancelled_and_resumed(tmp_path, qt):
    path = source_image(tmp_path, 1600, 1600)
    pyramid = Pyramid(path, 1600, 1600, tmp_path / "cache")
    cancel = threading.Event()
    cancel.set()
    pyramid.build(cancel, lambda value, message: None)
    assert not pyramid.complete()
    pyramid.build(threading.Event(), lambda value, message: None)
    assert pyramid.complete()


def test_edge_tiles_are_cropped_not_padded(tmp_path, qt):
    path = source_image(tmp_path, 700, 600)
    pyramid = Pyramid(path, 700, 600, tmp_path / "cache")
    pyramid.build(threading.Event(), lambda value, message: None)
    with Image.open(pyramid.tile_path(0, 1, 1)) as corner:
        assert corner.size == (700 - TILE, 600 - TILE)


def test_level_for_scale_picks_matching_resolution(tmp_path, qt):
    path = source_image(tmp_path, 4096, 4096)
    pyramid = Pyramid(path, 4096, 4096, tmp_path / "cache")
    assert pyramid.level_for_scale(1.0) == 0
    assert pyramid.level_for_scale(0.5) == 1
    assert pyramid.level_for_scale(0.25) == 2
    assert pyramid.level_for_scale(0.001) == pyramid.levels - 1


def test_compose_rebuilds_a_whole_level(tmp_path, qt):
    path = source_image(tmp_path, 1700, 900)
    pyramid = Pyramid(path, 1700, 900, tmp_path / "cache")
    pyramid.build(threading.Event(), lambda value, message: None)
    level = pyramid.preview_level(max_edge=1024)
    assert max(pyramid.level_size(level)) <= 1024
    image = pyramid.compose(level)
    assert (image.width(), image.height()) == pyramid.level_size(level)
    assert image.pixelColor(5, 5).blue() > 150


def test_cache_key_follows_the_file(tmp_path):
    path = source_image(tmp_path, 600, 600)
    first = pyramid_key(path)
    assert first == pyramid_key(path)
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    assert pyramid_key(path) != first


def test_tile_cache_respects_its_budget(tmp_path, qt):
    path = source_image(tmp_path, 2000, 2000)
    pyramid = Pyramid(path, 2000, 2000, tmp_path / "cache")
    pyramid.build(threading.Event(), lambda value, message: None)
    cache = TileCache(budget=TILE * TILE * 4 * 2)
    for col in range(4):
        assert cache.get(pyramid, 0, col, 0) is not None
    assert len(cache._entries) <= 2
    assert cache.get(pyramid, 0, 99, 99) is None


def test_sixteen_bit_and_tiff_sources_are_viewable(tmp_path, qt):
    from lannotex.workers import FORMATS, decode, to_rgb

    assert {".tif", ".tiff", ".bmp"} <= FORMATS

    deep = Image.new("I;16", (800, 600))
    deep.putdata([900 + (i % 400) for i in range(800 * 600)])
    shown = to_rgb(deep)
    assert shown.mode == "RGB"
    assert shown.getextrema()[0] == (0, 255), "a narrow 16-bit range must be stretched, not clipped"

    path = tmp_path / "deep.tif"
    deep.save(path)
    preview = decode(path)
    assert preview.width() == 800 and not preview.isNull()

    pyramid = Pyramid(path, 800, 600, tmp_path / "cache")
    pyramid.build(threading.Event(), lambda value, message: None)
    assert pyramid.complete()
    assert pyramid.compose(pyramid.preview_level()) is not None


def test_prune_drops_whole_pyramids(tmp_path, qt):
    root = tmp_path / "cache"
    for i in range(3):
        path = source_image(tmp_path, 1200, 1200, f"img{i}.png")
        Pyramid(path, 1200, 1200, root).build(threading.Event(), lambda value, message: None)
    before = sum(f.stat().st_size for f in root.rglob("*.jpg"))
    assert before > 0
    assert prune(root, budget=0) == 0
    assert not list(root.rglob("*.jpg"))
