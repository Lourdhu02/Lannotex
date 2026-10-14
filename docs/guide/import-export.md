# Import & export

## Export formats

| Format | Contains | Use it for |
| --- | --- | --- |
| **Labelme JSON** | One JSON per image: boxes as `rectangle`, polygons, classes as `flags` | LabelMe and tools that read its format |
| **YOLO boxes** | Ready-to-train Ultralytics dataset: `images/`, `labels/`, `data.yaml` | YOLO detection training |
| **COCO JSON** | One `coco.json` with boxes, polygon segmentations, and areas | Detection and instance segmentation |
| **Classification CSV** | One row per image, one 0/1 column per class | Image classification |
| **Native JSONL** | Every annotation with its ID and status | Lossless backup and round-trips |

Shapes that a format can't represent are counted and reported, not silently dropped:
YOLO boxes skips polygons and classes, COCO skips classes, and the CSV skips shapes.

### Output layout

Each export creates a new folder, so earlier exports are never overwritten:

```text
Lannotex-export-1a2b3c4d/
├── manifest.json          # format, counts, skipped images and reasons
├── classes.json           # label list; YOLO class IDs follow this order
├── classification.csv
├── images.jsonl
├── annotations.jsonl
└── 00000001_street.json   # per-image files (Labelme JSON)
```

Images are **referenced, not copied**: exported records point to the original files. YOLO
is the exception, described below.

### What gets skipped

An image is left out of the export, and listed in `manifest.json`, if:

- its source file is missing,
- an annotation fails validation, or
- it has an unsaved recovery draft. Save it first.

Run **View → Analysis** or `lannotex analyze` beforehand to find these images.

### YOLO: ready to train

The YOLO export is a complete [Ultralytics](https://docs.ultralytics.com/datasets/detect/)
dataset:

```text
Lannotex-export-1a2b3c4d/
├── data.yaml              # path, train/val, class names
├── images/00000001_street.jpg
└── labels/00000001_street.txt   # class cx cy w h, normalized
```

```bash
yolo detect train data=Lannotex-export-1a2b3c4d/data.yaml model=yolo11n.pt
```

- Images are **hard-linked** into `images/` when the export is on the same drive, so they
  take no extra space. Otherwise they're copied. Your originals are never modified.
- Images marked **No target objects** get an empty label file, so YOLO learns them as
  background.
- Images you haven't annotated yet are **left out**. If they were included, YOLO would
  treat them as "nothing here".
- `train` and `val` point at the same images. Split them yourself for a real evaluation.
- If you move the export folder, update `path:` in `data.yaml`.

## Importing annotations

**Project → Import annotations…** accepts:

- a **Labelme JSON** file, or a folder of them (top level only), and
- a **native JSONL** export.

Each referenced image is checked: it must exist, and its dimensions must match the
annotation file. Labels you don't have yet are created. An image that already has
annotations or a draft in the project is **skipped, never overwritten**. Errors are
listed per file.

See [Coming from LabelMe](../migrate-from-labelme.md) for which LabelMe shape types are
supported.

## Headless export

```bash
lannotex export ./my-dataset ./exports --format "COCO JSON"
```

See [Command line](../cli.md).
