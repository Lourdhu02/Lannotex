"""Read datasets written by other tools: LabelMe, COCO, YOLO, Pascal VOC and Lannotex's own JSONL.

Every reader yields the same record so one ingest loop can serve them all:
``(image_path, width, height, annotations, negative)``. A shape that Lannotex cannot represent
is counted and skipped rather than failing the file it came from.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

from .domain import Annotation, validate, validate_all

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp")


def detect_format(source: Path) -> str:
    source = Path(source)
    if source.is_dir():
        if (source / "data.yaml").is_file() or (source / "data.yml").is_file():
            return "yolo"
        if (source / "Annotations").is_dir() and any((source / "Annotations").glob("*.xml")):
            return "voc"
        if any(source.glob("*.xml")):
            return "voc"
        if next(source.rglob("*.json"), None) is not None:
            first = next(source.rglob("*.json"))
            return "coco" if _looks_like_coco(first) else "labelme"
        if (source / "labels").is_dir() and (source / "images").is_dir():
            return "yolo"
        raise ValueError("No LabelMe, COCO, YOLO or VOC data found in this folder")
    if source.suffix == ".jsonl":
        return "native"
    if source.suffix == ".xml":
        return "voc"
    if source.suffix == ".json":
        return "coco" if _looks_like_coco(source) else "labelme"
    raise ValueError(f"Unsupported annotation file: {source.name}")


def _looks_like_coco(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8") as stream:
            head = stream.read(4096)
    except OSError:
        return False
    return '"categories"' in head and '"annotations"' in head and '"images"' in head


def _keep(annotation, skipped: Counter, context: str) -> bool:
    problems = validate(annotation, {annotation.label})
    if problems:
        skipped[f"{context}: {problems[0].lower()}"] += 1
        return False
    return True


def _unit(value, size):
    return min(1.0, max(0.0, value / size))


def read_coco(source: Path, skipped: Counter):
    """COCO file_name is relative to the dataset's images folder."""
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    base = Path(source).parent
    names = {c["id"]: c["name"] for c in data.get("categories", ())}
    by_image: dict[int, list] = {}
    for entry in data.get("annotations", ()):
        by_image.setdefault(entry["image_id"], []).append(entry)
    for image in data.get("images", ()):
        width, height = image.get("width"), image.get("height")
        if not width or not height:
            skipped["COCO images without a size"] += 1
            continue
        path = _locate(base, image["file_name"])
        if path is None:
            skipped["COCO images whose file is missing"] += 1
            continue
        annotations = []
        for entry in by_image.get(image["id"], ()):
            label = names.get(entry.get("category_id"), str(entry.get("category_id")))
            segmentation = entry.get("segmentation")
            if isinstance(segmentation, dict):
                skipped["COCO RLE masks (not supported yet)"] += 1
                continue
            if segmentation and isinstance(segmentation, list) and segmentation[0]:
                flat = segmentation[0]
                points = [[_unit(flat[i], width), _unit(flat[i + 1], height)] for i in range(0, len(flat) - 1, 2)]
                shape = Annotation(label, "polygon", points)
            elif entry.get("bbox"):
                x, y, w, h = entry["bbox"]
                shape = Annotation(
                    label, "box", [_unit(x, width), _unit(y, height), _unit(x + w, width), _unit(y + h, height)]
                )
            else:
                skipped["COCO annotations without geometry"] += 1
                continue
            if _keep(shape, skipped, "COCO " + shape.kind):
                annotations.append(shape)
        yield str(path), width, height, annotations, not annotations


def _locate(base: Path, file_name: str):
    candidates = [
        base / file_name,
        base / "images" / file_name,
        base / Path(file_name).name,
        base / "images" / Path(file_name).name,
    ]
    return next((c for c in candidates if c.is_file()), None)


def parse_names(text: str) -> list[str]:
    """The small slice of YAML that a YOLO data file uses for class names."""
    names: dict[int, str] = {}
    listed: list[str] = []
    inside = False
    for raw in text.splitlines():
        line = raw.split("#")[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("names:"):
            inside = True
            rest = line[len("names:") :].strip()
            if rest.startswith("["):
                listed = [v.strip().strip("'\"") for v in rest.strip("[]").split(",") if v.strip()]
                inside = False
            continue
        if inside:
            if not line.startswith((" ", "\t")):
                break
            body = line.strip()
            if body.startswith("-"):
                listed.append(body[1:].strip().strip("'\""))
            elif ":" in body:
                index, _, value = body.partition(":")
                try:
                    names[int(index.strip())] = value.strip().strip("'\"")
                except ValueError:
                    continue
    if names:
        return [names[k] for k in sorted(names)]
    return listed


def read_yolo(folder: Path, skipped: Counter):
    from PIL import Image

    folder = Path(folder)
    config = next((folder / n for n in ("data.yaml", "data.yml") if (folder / n).is_file()), None)
    names = parse_names(config.read_text(encoding="utf-8")) if config else []
    if not names:
        classes = next((folder / n for n in ("classes.txt", "classes.json") if (folder / n).is_file()), None)
        if classes and classes.suffix == ".json":
            names = json.loads(classes.read_text(encoding="utf-8"))
        elif classes:
            names = [line.strip() for line in classes.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not names:
        raise ValueError("No class names found: expected names in data.yaml, or classes.txt")

    for label_file in sorted(folder.rglob("*.txt")):
        if label_file.name in ("classes.txt",) or "labels" not in label_file.parts:
            continue
        image = _yolo_image(label_file, skipped)
        if image is None:
            continue
        with Image.open(image) as handle:
            width, height = handle.size
        annotations = []
        for line in label_file.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if not fields:
                continue
            try:
                index = int(float(fields[0]))
                values = [float(v) for v in fields[1:]]
            except ValueError:
                skipped["YOLO lines that are not numbers"] += 1
                continue
            label = names[index] if 0 <= index < len(names) else str(index)
            if len(values) == 4:
                cx, cy, w, h = values
                shape = Annotation(
                    label,
                    "box",
                    [max(0.0, cx - w / 2), max(0.0, cy - h / 2), min(1.0, cx + w / 2), min(1.0, cy + h / 2)],
                )
            elif len(values) >= 6 and len(values) % 2 == 0:
                shape = Annotation(
                    label,
                    "polygon",
                    [
                        [min(1.0, max(0.0, values[i])), min(1.0, max(0.0, values[i + 1]))]
                        for i in range(0, len(values) - 1, 2)
                    ],
                )
            else:
                skipped["YOLO lines with an unexpected field count"] += 1
                continue
            if _keep(shape, skipped, "YOLO " + shape.kind):
                annotations.append(shape)
        yield str(image), width, height, annotations, not annotations


def _yolo_image(label_file: Path, skipped: Counter):
    parts = list(label_file.parts)
    index = len(parts) - 1 - parts[::-1].index("labels")
    parts[index] = "images"
    stem = Path(*parts).with_suffix("")
    for suffix in IMAGE_SUFFIXES:
        candidate = stem.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    skipped["YOLO labels with no matching image"] += 1
    return None


def read_voc(source: Path, skipped: Counter):
    source = Path(source)
    files = (
        [source]
        if source.suffix == ".xml"
        else sorted(
            (source / "Annotations").glob("*.xml") if (source / "Annotations").is_dir() else source.glob("*.xml")
        )
    )
    for xml_file in files:
        try:
            root = ElementTree.parse(xml_file).getroot()
        except ElementTree.ParseError:
            skipped["VOC files that are not valid XML"] += 1
            continue
        size = root.find("size")
        if size is None:
            skipped["VOC files without a size"] += 1
            continue
        width, height = int(float(size.findtext("width", "0"))), int(float(size.findtext("height", "0")))
        if width <= 0 or height <= 0:
            skipped["VOC files without a size"] += 1
            continue
        image = _voc_image(xml_file, root)
        if image is None:
            skipped["VOC files whose image is missing"] += 1
            continue
        annotations = []
        for obj in root.findall("object"):
            box = obj.find("bndbox")
            if box is None:
                skipped["VOC objects without a bndbox"] += 1
                continue
            try:
                left, top = float(box.findtext("xmin", "0")), float(box.findtext("ymin", "0"))
                right, bottom = float(box.findtext("xmax", "0")), float(box.findtext("ymax", "0"))
            except ValueError:
                skipped["VOC objects with unreadable coordinates"] += 1
                continue
            # VOC pixel indices start at 1.
            shape = Annotation(
                obj.findtext("name", "object").strip(),
                "box",
                [_unit(left - 1, width), _unit(top - 1, height), _unit(right, width), _unit(bottom, height)],
            )
            if _keep(shape, skipped, "VOC box"):
                annotations.append(shape)
        yield str(image), width, height, annotations, not annotations


def read_native(source: Path, note):
    with Path(source).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            try:
                record = json.loads(line)
                image = record["image"]
                yield (
                    image["file_name"],
                    image["width"],
                    image["height"],
                    [Annotation.from_dict(a) for a in record["annotations"]],
                    record["status"] == "empty",
                )
            except Exception as error:
                note(f"{Path(source).name} line {number}", error)


def read_labelme(source: Path, skipped: Counter, note, cancel):
    from .exporters import parse_labelme

    source = Path(source)
    # One malformed file must not abort the rest of the folder.
    files = sorted(source.rglob("*.json")) if source.is_dir() else [source]
    for file in files:
        if cancel.is_set():
            return
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "shapes" not in data:
                continue
            annotations, negative = parse_labelme(data, skipped)
            yield (
                str((file.parent / data["imagePath"]).resolve()),
                data["imageWidth"],
                data["imageHeight"],
                annotations,
                negative,
            )
        except Exception as error:
            note(file, error)


def import_annotations(root, source, cancel, progress, fmt="auto"):
    """Import LabelMe, COCO, YOLO, Pascal VOC or native JSONL. Existing labelled images are
    never overwritten, and a shape this tool cannot represent is counted, not fatal."""
    from PIL import Image

    from .storage import Project

    project = Project(root, create=False)
    source = Path(source)
    count, errors, skipped = 0, [], Counter()

    def note(where, error):
        if len(errors) < 100:
            errors.append(f"{where}: {error}")

    try:
        detected = detect_format(source) if fmt == "auto" else fmt
        if detected == "native":
            records = read_native(source, note)
        elif detected == "coco":
            records = read_coco(source, skipped)
        elif detected == "yolo":
            records = read_yolo(source, skipped)
        elif detected == "voc":
            records = read_voc(source, skipped)
        else:
            records = read_labelme(source, skipped, note, cancel)

        for path, width, height, annotations, negative in records:
            if cancel.is_set():
                break
            try:
                with Image.open(path) as image:
                    size = image.size
                    if image.getexif().get(274, 1) in (5, 6, 7, 8):
                        size = size[::-1]
                    if size != (width, height):
                        raise ValueError("Source dimensions differ from annotation metadata")
                problems = validate_all(annotations, {a.label for a in annotations}, negative)
                if problems:
                    raise ValueError("; ".join(problems))
                reference = project.reference(path)
                existing = project.conn.execute("SELECT * FROM images WHERE path=?", (reference,)).fetchone()
                if existing and (
                    existing["status"] != "new"
                    or project.conn.execute("SELECT 1 FROM drafts WHERE image_id=?", (existing["id"],)).fetchone()
                ):
                    raise ValueError("Image already has annotations or a draft; skipped")
                known = {r["name"] for r in project.labels()}
                for label in {a.label for a in annotations} - known:
                    project.add_label(label)
                ident = project.add_image(path, width, height)
                project.save_annotations(ident, annotations, negative)
                count += 1
                progress(count, f"Imported annotations for {count} images")
            except Exception as error:
                note(path, error)
        return {
            "added": count,
            "errors": errors,
            "cancelled": cancel.is_set(),
            "skipped_shapes": dict(skipped),
            "format": detected,
        }
    finally:
        project.close()


def _voc_image(xml_file: Path, root):
    name = (root.findtext("filename") or "").strip()
    base = xml_file.parent
    roots = [base, base.parent / "JPEGImages", base.parent / "images", base.parent]
    for folder in roots:
        if name:
            candidate = folder / name
            if candidate.is_file():
                return candidate
        for suffix in IMAGE_SUFFIXES:
            candidate = folder / (xml_file.stem + suffix)
            if candidate.is_file():
                return candidate
    return None
