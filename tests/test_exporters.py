"""Exporter primitives and headless project export."""
import json
from pathlib import Path
import threading
from xml.etree import ElementTree

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


def detection_project(tmp_path, count=12):
    from PIL import Image as PILImage
    root = tmp_path / "project"
    p = Project(root)
    p.add_label("cat")
    p.add_label("dog")
    ids = []
    for i in range(count):
        path = root / f"img{i}.png"
        PILImage.new("RGB", (200, 100)).save(path)
        ident = p.add_image(path, 200, 100)
        p.save_annotations(ident, [Annotation("dog", "box", [.1, .2, .5, .6]),
                                   Annotation("cat", "polygon", [[.1, .1], [.9, .1], [.9, .8]])])
        ids.append(ident)
    p.close()
    return root, ids


def test_coco_file_name_is_relative_and_images_are_exported(tmp_path):
    root, _ = detection_project(tmp_path, count=2)
    result = export_project(root, tmp_path / "out", "COCO JSON", threading.Event(), lambda *a: None)
    out = Path(result["path"])
    coco = json.loads((out / "coco.json").read_text())
    assert result["included"] == 2
    for entry in coco["images"]:
        assert not Path(entry["file_name"]).is_absolute()
        assert (out / "images" / entry["file_name"]).is_file(), "file_name must resolve inside the export"
    assert {c["name"] for c in coco["categories"]} == {"cat", "dog"}
    assert coco["annotations"] and all(a["image_id"] for a in coco["annotations"])


def test_yolo_split_is_deterministic_and_covers_every_set(tmp_path):
    root, _ = detection_project(tmp_path, count=12)
    first = export_project(root, tmp_path / "a", "YOLO boxes", threading.Event(), lambda *a: None, split=True, seed=7)
    second = export_project(root, tmp_path / "b", "YOLO boxes", threading.Event(), lambda *a: None, split=True, seed=7)
    assert first["split"] == second["split"]
    assert sum(first["split"].values()) == first["included"] == 12
    assert all(count > 0 for count in first["split"].values())

    out = Path(first["path"])
    data = (out / "data.yaml").read_text()
    for name in ("train", "val", "test"):
        assert f"{name}: images/{name}" in data
        images = sorted(p.stem for p in (out / "images" / name).iterdir())
        labels = sorted(p.stem for p in (out / "labels" / name).iterdir())
        assert images == labels and images

    from lannotex.exporters import split_for
    assert any(split_for(i, 7) != split_for(i, 99) for i in range(20)), "the seed must change the assignment"
    assert all(split_for(i, 7) == split_for(i, 7) for i in range(20))


def test_yolo_without_split_keeps_one_set(tmp_path):
    root, _ = detection_project(tmp_path, count=3)
    result = export_project(root, tmp_path / "out", "YOLO boxes", threading.Event(), lambda *a: None)
    out = Path(result["path"])
    assert "split" not in result
    assert (out / "images").is_dir() and not (out / "images" / "train").exists()
    assert "train: images\nval: images" in (out / "data.yaml").read_text()


def test_tiny_dataset_still_gets_a_val_set(tmp_path):
    root, _ = detection_project(tmp_path, count=3)
    result = export_project(root, tmp_path / "out", "YOLO boxes", threading.Event(), lambda *a: None, split=True, seed=1)
    out = Path(result["path"])
    assert result["split"]["train"] >= 1 and result["split"]["val"] >= 1
    for name in ("train", "val"):
        images = {p.stem for p in (out / "images" / name).iterdir()}
        labels = {p.stem for p in (out / "labels" / name).iterdir()}
        assert images == labels and images


def test_yolo_segments_export_writes_polygons(tmp_path):
    root, _ = detection_project(tmp_path, count=2)
    result = export_project(root, tmp_path / "out", "YOLO segments", threading.Event(), lambda *a: None)
    out = Path(result["path"])
    assert result["included"] == 2
    assert result["unsupported_annotations"] == 2, "the box on each image cannot be a segment"
    line = next((out / "labels").glob("*.txt")).read_text().strip()
    fields = line.split()
    assert fields[0] == "0" and len(fields) == 7  # class + three xy pairs
    assert all(0 <= float(v) <= 1 for v in fields[1:])


def test_pascal_voc_export(tmp_path):
    root, _ = detection_project(tmp_path, count=2)
    result = export_project(root, tmp_path / "out", "Pascal VOC", threading.Event(), lambda *a: None)
    out = Path(result["path"])
    assert result["included"] == 2
    xml_path = next((out / "Annotations").glob("*.xml"))
    tree = ElementTree.parse(xml_path).getroot()
    assert tree.find("size/width").text == "200" and tree.find("size/height").text == "100"
    names = sorted(o.find("name").text for o in tree.findall("object"))
    assert names == ["cat", "dog"], "a polygon is written as its bounding box"
    box = tree.find("object/bndbox")
    assert 1 <= int(box.find("xmin").text) <= int(box.find("xmax").text) <= 200
    assert (out / "JPEGImages" / tree.find("filename").text).is_file()
    listed = (out / "ImageSets" / "Main" / "default.txt").read_text().split()
    assert len(listed) == 2 and all((out / "Annotations" / f"{n}.xml").is_file() for n in listed)


def test_voc_xml_escapes_label_text():
    from lannotex.exporters import voc_xml
    xml = voc_xml("a.png", 10, 10, [Annotation("a & <b>", "box", [0, 0, 1, 1])])
    assert "a &amp; &lt;b&gt;" in xml
    assert ElementTree.fromstring(xml).find("object/name").text == "a & <b>"


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
