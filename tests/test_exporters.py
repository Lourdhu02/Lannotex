"""Exporter primitives and headless project export."""
from pathlib import Path
import threading

from lannotex.domain import Annotation
from lannotex.exporters import coco_record, export_project, labelme_data, parse_labelme, yolo_line
from lannotex.storage import Project


def test_labelme_round_trip_preserves_ids_and_geometry():
    anns = [Annotation("cat", "box", [.1, .2, .5, .6]),
            Annotation("dog", "polygon", [[0, 0], [1, 0], [1, 1]])]
    data = labelme_data("img.png", 100, 50, anns, negative=False)
    assert data["lannotex"]["version"] == "0.0.2"
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
