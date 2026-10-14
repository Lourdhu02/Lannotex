# LabelReview Desktop 0.0.1

Fast, offline-first annotation for classifications, boxes, and polygons. Projects are local SQLite databases; source images are never altered or uploaded.

## Install and run

Requires Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .[dev]
labelreview
```

The first action is **Open project**, which selects (or creates) a project directory. Then choose **Import folder**, add labels, and annotate. Projects retain absolute image references in this initial release; if a file is moved, select the original image folder again and re-import to restore it.

## Controls

`B` box, `P` polygon, `V` select, `Enter` finish polygon, `Escape` cancel drawing, `Delete` delete selection, `F` fit, `Ctrl+S` save, and `Ctrl+Enter` save and next. The canvas zooms under the pointer with the wheel. Autosave has a 700 ms debounce.

## Build a portable Windows app

```powershell
.\scripts\build_windows.ps1
```

This creates `dist\LabelReview\LabelReview.exe`, which runs without a separate Python install. Validate this directory on a clean Windows VM before distribution. The app stores project files only in the project directory; it does not write project data into the installation directory.

## Architecture

- `domain.py`: normalized annotation model and geometry validation
- `storage.py`: SQLite schema migration and transactional writes
- `exporters.py`: Labelme, YOLO coordinate, and COCO record conversion primitives
- `app.py`: Qt UI and graphics canvas

## Scope and known limitations

v0.0.1 is a functional local MVP, not a complete Labelme replacement. It includes classification data model support, boxes and new polygon drawing, explicit/debounced persistence, and reopening editable boxes. It does **not yet** provide a production-grade background importer/thumbnail cache, polygon vertex editing/reload rendering, undo/redo, configurable bindings/themes/layout persistence, project archive/restore/relink UI, full export wizard/analysis page, or finished Microsoft Store packaging. These remain the priority work before claiming support for 10 GB datasets.

Future paid desktop features must be optional: local projects and exports remain accessible independently of any future entitlement or cloud service.
