"""Exporter primitives and headless project export."""
import json
from pathlib import Path
import threading

from PIL import Image

from lannotex import __version__
from lannotex.domain import Annotation
from lannotex.exporters import coco_record, export_project, labelme_data, parse_labelme, yolo_line
from lannotex.storage import Project


def test_labelme_round_trip_preserves_ids_and_geometry():
    anns = [Annotation("cat", "box", [.1, .2, .5, .6]),
            Annotation("dog", "polygon", [[0, 0], [1, 0], [1, 1]])]
    data = labelme_data("img.png", 100, 50, anns, negative=False)
    assert data["lannotex"]["version"] == __version__
    parsed, negative = parse_labelme(data)
    assert not negative
    assert [a.label for a in parsed] == ["cat", "dog"]
    assert parsed[0].geometry == [.1, .2, .5, .6]
    assert parsed[0].id == anns[0].id
    assert parsed[1].id == anns[1].id


def test_parse_labelme_accepts_legacy_labelreview_keys():
    data = {
        "imageWidth": 100, "imageHeight": 50,
        "shapes": [{"label": "cat", "shape_type": "rectangle",
                    "points": [[10, 10], [50, 40]], "labelreview_id": "legacy-1"}],
    }
    anns, negative = parse_labelme(data)
    assert not negative
    assert anns[0].id == "legacy-1"
    assert anns[0].geometry == [.1, .2, .5, .8]


def test_parse_labelme_converts_circles_and_rotations_and_skips_the_rest():
    from collections import Counter
    data = {"imageWidth": 200, "imageHeight": 100, "shapes": [
        {"label": "ball", "shape_type": "circle", "points": [[100, 50], [120, 50]]},
        {"label": "car", "shape_type": "rotation", "points": [[10, 10], [60, 20], [55, 45], [5, 35]]},
        {"label": "nose", "shape_type": "point", "points": [[30, 30]]},
        {"label": "lane", "shape_type": "linestrip", "points": [[0, 0], [50, 50], [90, 20]]},
        {"label": "bad", "shape_type": "polygon", "points": [[0, 0], [10, 0]]},
    ]}
    skipped = Counter()
    anns, negative = parse_labelme(data, skipped)
    assert [(a.label, a.kind) for a in anns] == [("ball", "polygon"), ("car", "polygon")]
    xs = [p[0]*200 for p in anns[0].geometry]; assert len(anns[0].geometry) == 32 and abs(max(xs)-120) < 1e-6
    assert skipped == Counter({"point shapes (not supported yet)": 1, "linestrip shapes (not supported yet)": 1,
                               "polygon: polygon needs 3–1000 vertices": 1})


def test_parse_labelme_reads_legacy_no_targets_flag():
    data = {"imageWidth": 100, "imageHeight": 50, "shapes": [],
            "labelreview": {"no_targets": True}}
    anns, negative = parse_labelme(data)
    assert negative is True and anns == []


def test_yolo_line_normalized_center():
    assert yolo_line(Annotation("cat", "box", [.1, .2, .5, .6]), 2) == \
        "2 0.300000 0.400000 0.400000 0.400000"


def test_coco_record_pixel_bbox_and_categories():
    image = {"id": 1, "file_name": "a.png", "width": 100, "height": 100}
    record = coco_record(image, [Annotation("cat", "box", [0, 0, .5, .5])], ["cat", "dog"])
    assert record["categories"] == [{"id": 1, "name": "cat"}, {"id": 2, "name": "dog"}]
    assert record["annotations"][0]["bbox"] == [0, 0, 50, 50]


def test_export_project_empty_creates_manifest(tmp_path):
    root = tmp_path / "project"; dest = tmp_path / "out"
    project = Project(root); project.add_label("cat"); project.close()
    result = export_project(str(root), str(dest), "Native JSONL", threading.Event(), lambda v, m: None)
    assert result["included"] == 0 and result["errors"] == []
    out = Path(result["path"])
    assert (out / "classes.json").exists()
    assert (out / "manifest.json").exists()
    assert (out / "images.jsonl").exists()


def test_yolo_export_is_ultralytics_ready(tmp_path):
    src = tmp_path / "imgs"; src.mkdir()
    Image.new("RGB", (200, 100)).save(src / "a.png")
    Image.new("RGB", (50, 50)).save(src / "b.jpg")
    Image.new("RGB", (50, 50)).save(src / "c.png")
    root = tmp_path / "project"; p = Project(root); p.add_label("cat"); p.add_label("dog")
    a = p.add_image(src / "a.png", 200, 100); b = p.add_image(src / "b.jpg", 50, 50); p.add_image(src / "c.png", 50, 50)
    p.save_annotations(a, [Annotation("dog", "box", [.1, .2, .5, .6]), Annotation("cat", "polygon", [[0, 0], [1, 0], [1, 1]])])
    p.save_annotations(b, [], negative=True)
    p.close()

    result = export_project(root, tmp_path / "out", "YOLO boxes", threading.Event(), lambda *args: None)
    out = Path(result["path"])
    assert result["included"] == 2 and result["unlabeled"] == 1 and result["unsupported_annotations"] == 1
    images = sorted(f.name for f in (out / "images").iterdir())
    labels = sorted(f.name for f in (out / "labels").iterdir())
    assert [Path(n).stem for n in images] == [Path(n).stem for n in labels] and len(images) == 2
    assert (out / "labels" / labels[0]).read_text() == "1 0.300000 0.400000 0.400000 0.400000\n"
    assert (out / "labels" / labels[1]).read_text() == ""
    data = (out / "data.yaml").read_text()
    assert "train: images" in data and '0: "cat"' in data and '1: "dog"' in data
    assert json.loads(data.split("path: ")[1].splitlines()[0]) == str(out.resolve())
