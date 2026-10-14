---
hide:
  - navigation
---

# Lannotex

**Fast, offline-first image annotation for classifications, bounding boxes, and polygons, on your own machine.**

Lannotex is a free, MIT-licensed desktop app. Each project is one SQLite file in a folder you
choose. Your source images are never moved, copied, or altered. There is no account, no
telemetry, and no network traffic unless you deliberately host or join a team.

[Install Lannotex](getting-started/installation.md){ .md-button .md-button--primary }
[Coming from LabelMe?](migrate-from-labelme.md){ .md-button }

## Why Lannotex

<div class="grid cards" markdown>

-   :material-database-lock:{ .lg .middle } **Projects that scale**

    ---

    One `project.sqlite3` per dataset instead of thousands of JSON files. The image list is
    virtualized: it keeps at most 1,024 records in memory, whether the dataset has 300
    images or 100,000.

-   :material-content-save-check:{ .lg .middle } **You don't lose work**

    ---

    Every edit goes to a recovery draft, autosave runs 700 ms after you stop, and saves are
    transactional. Invalid geometry, such as self-intersecting polygons or zero-size boxes,
    is rejected before it reaches your dataset.

-   :material-export:{ .lg .middle } **Every common format, free**

    ---

    Export to Labelme JSON, YOLO, COCO, classification CSV, or a lossless native JSONL. You
    can export from the app or headlessly with `lannotex export` in CI.

-   :material-account-group:{ .lg .middle } **Optional teams, no cloud**

    ---

    Host a project on your LAN, invite reviewers with private tokens, and sync in the
    background. A stale save becomes a conflict you resolve; it never silently overwrites
    someone else's work.

</div>

## At a glance

| | |
| --- | --- |
| **Annotation types** | Whole-image classes (multi-label), bounding boxes, polygons |
| **Pipelines** | Classification, detection, segmentation, or combined |
| **Platforms** | Windows, macOS, Linux; Python 3.11–3.13 or standalone binaries |
| **Exports** | Labelme JSON, YOLO boxes, COCO JSON, classification CSV, native JSONL |
| **Imports** | Images (JPEG, PNG, WebP), Labelme JSON, native JSONL |
| **License** | MIT |

## Where to next

- **New to annotation tools?** Start with the [quick start](getting-started/quickstart.md).
- **Have a LabelMe dataset?** See [Coming from LabelMe](migrate-from-labelme.md).
- **Automating a pipeline?** See the [command line](cli.md).
- **Labeling with others?** Read [team projects](TEAM.md).
