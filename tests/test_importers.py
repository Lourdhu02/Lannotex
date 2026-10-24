"""Reading datasets written by other tools, including round-trips through our own exports."""

import threading
from pathlib import Path

import pytest
from PIL import Image

from lannotex.domain import Annotation
from lannotex.exporters import export_project
from lannotex.importers import detect_format, import_annotations, parse_names
from lannotex.storage import Project

BOX = [0.1, 0.2, 0.5, 0.6]
POLYGON = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.8]]


def seeded_project(tmp_path, name="project", count=4, polygons=True):
    root = tmp_path / name
    project = Project(root)
    project.add_label("cat")
    project.add_label("dog")
    for i in range(count):
        path = root / f"img{i}.png"
        Image.new("RGB", (200, 100), "#406080").save(path)
        ident = project.add_image(path, 200, 100)
        shapes = [Annotation("dog", "box", list(BOX))]
        if polygons:
            shapes.append(Annotation("cat", "polygon", [list(p) for p in POLYGON]))
        project.save_annotations(ident, shapes)
    project.close()
    return root


def empty_project(tmp_path, name):
    root = tmp_path / name
    Project(root).close()
    return root


def run_import(target, source, fmt="auto"):
    return import_annotations(target, source, threading.Event(), lambda *a: None, fmt=fmt)


def test_detect_format(tmp_path):
    folder = tmp_path / "ds"
    (folder / "Annotations").mkdir(parents=True)
    (folder / "Annotations" / "a.xml").write_text("<annotation/>")
    assert detect_format(folder) == "voc"

    yolo = tmp_path / "yolo"
    yolo.mkdir()
    (yolo / "data.yaml").write_text("names:\n  0: cat\n")
    assert detect_format(yolo) == "yolo"

    coco = tmp_path / "c.json"
    coco.write_text('{"images": [], "annotations": [], "categories": []}')
    assert detect_format(coco) == "coco"

    labelme = tmp_path / "l.json"
    labelme.write_text('{"shapes": [], "imagePath": "x.png"}')
    assert detect_format(labelme) == "labelme"

    assert detect_format(tmp_path / "x.jsonl") == "native"
    with pytest.raises(ValueError):
        detect_format(tmp_path / "x.txt")


def test_parse_names_handles_both_yaml_shapes():
    assert parse_names('names:\n  0: "cat"\n  1: dog\nnc: 2\n') == ["cat", "dog"]
    assert parse_names("names: ['cat', 'dog']\n") == ["cat", "dog"]
    assert parse_names("names:\n  - cat\n  - dog\n") == ["cat", "dog"]
    assert parse_names("path: x\n") == []


def test_coco_round_trip(tmp_path):
    source = seeded_project(tmp_path, "src")
    exported = export_project(source, tmp_path / "out", "COCO JSON", threading.Event(), lambda *a: None)
    target = empty_project(tmp_path, "dst")

    result = run_import(target, Path(exported["path"]) / "coco.json")
    assert result["format"] == "coco"
    assert result["added"] == 4 and not result["errors"]

    project = Project(target, create=False)
    try:
        assert {r["name"] for r in project.labels()} == {"cat", "dog"}
        for row in project.images():
            kinds = sorted(a.kind for a in project.load_annotations(row["id"]))
            assert kinds == ["box", "polygon"]
            box = next(a for a in project.load_annotations(row["id"]) if a.kind == "box")
            assert all(abs(got - want) < 0.01 for got, want in zip(box.geometry, BOX))
    finally:
        project.close()


def test_yolo_round_trip_with_split(tmp_path):
    source = seeded_project(tmp_path, "src", count=6, polygons=False)
    exported = export_project(
        source, tmp_path / "out", "YOLO boxes", threading.Event(), lambda *a: None, split=True, seed=5
    )
    target = empty_project(tmp_path, "dst")

    result = run_import(target, Path(exported["path"]))
    assert result["format"] == "yolo"
    assert result["added"] == 6, "every split folder must be read"

    project = Project(target, create=False)
    try:
        assert {r["name"] for r in project.labels()} == {"dog"}
        for row in project.images():
            shapes = project.load_annotations(row["id"])
            assert len(shapes) == 1 and shapes[0].label == "dog"
            assert all(abs(got - want) < 0.01 for got, want in zip(shapes[0].geometry, BOX))
    finally:
        project.close()


def test_yolo_segments_round_trip(tmp_path):
    source = seeded_project(tmp_path, "src", count=2)
    exported = export_project(source, tmp_path / "out", "YOLO segments", threading.Event(), lambda *a: None)
    target = empty_project(tmp_path, "dst")

    result = run_import(target, Path(exported["path"]))
    assert result["added"] == 2
    project = Project(target, create=False)
    try:
        shapes = project.load_annotations(project.images()[0]["id"])
        assert [a.kind for a in shapes] == ["polygon"]
        assert len(shapes[0].geometry) == 3
    finally:
        project.close()


def test_voc_round_trip(tmp_path):
    source = seeded_project(tmp_path, "src", count=3)
    exported = export_project(source, tmp_path / "out", "Pascal VOC", threading.Event(), lambda *a: None)
    target = empty_project(tmp_path, "dst")

    result = run_import(target, Path(exported["path"]))
    assert result["format"] == "voc"
    assert result["added"] == 3

    project = Project(target, create=False)
    try:
        shapes = project.load_annotations(project.images()[0]["id"])
        assert sorted(a.label for a in shapes) == ["cat", "dog"], "the polygon arrives as its box"
        assert all(a.kind == "box" for a in shapes)
        box = next(a for a in shapes if a.label == "dog")
        assert all(abs(got - want) < 0.02 for got, want in zip(box.geometry, BOX))
    finally:
        project.close()


def test_bad_shapes_are_counted_not_fatal(tmp_path):
    folder = tmp_path / "yolo"
    (folder / "images").mkdir(parents=True)
    (folder / "labels").mkdir(parents=True)
    Image.new("RGB", (100, 100)).save(folder / "images" / "a.png")
    (folder / "data.yaml").write_text("names:\n  0: cat\n")
    (folder / "labels" / "a.txt").write_text(
        "0 0.5 0.5 0.4 0.4\n"  # good box
        "0 0.5 0.5 0.0 0.0\n"  # zero area
        "cat 1 2 3 4\n"  # not numbers
        "0 0.1 0.1 0.2\n"  # wrong field count
    )
    target = empty_project(tmp_path, "dst")
    result = run_import(target, folder)
    assert result["added"] == 1
    reasons = result["skipped_shapes"]
    assert any("not numbers" in r for r in reasons)
    assert any("unexpected field count" in r for r in reasons)
    assert any("box" in r for r in reasons)


def test_import_does_not_overwrite_existing_work(tmp_path):
    source = seeded_project(tmp_path, "src", count=1)
    exported = export_project(source, tmp_path / "out", "COCO JSON", threading.Event(), lambda *a: None)
    first = run_import(empty_project(tmp_path, "dst"), Path(exported["path"]) / "coco.json")
    assert first["added"] == 1

    again = run_import(tmp_path / "dst", Path(exported["path"]) / "coco.json")
    assert again["added"] == 0
    assert any("already has annotations" in e for e in again["errors"])
