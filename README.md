# Lannotex

> Fast, offline-first image annotation for **classifications**, **bounding boxes**, and **polygons** — right on your own machine.

![PyPI - Version](https://img.shields.io/pypi/v/lannotex)
![Python](https://img.shields.io/pypi/pyversions/lannotex)
![License](https://img.shields.io/github/license/Lourdhu02/Lannotex)
![CI](https://img.shields.io/github/actions/workflow/status/Lourdhu02/Lannotex/ci.yml?label=CI)
![Platforms](https://img.shields.io/badge/Windows%20·%20macOS%20·%20Linux-supported-brightgreen)
[![stars](https://img.shields.io/github/stars/Lourdhu02/Lannotex?style=social)](https://github.com/Lourdhu02/Lannotex)

Lannotex is a local-first desktop annotation tool built with PySide6/Qt. Projects are
plain **SQLite databases** in a folder of your choice; source images are **never altered**.
Solo projects stay on disk. Optional team projects explicitly transfer images and
annotations between reviewer desktops and a host you choose. Export to Labelme, YOLO,
COCO, CSV, or Lannotex's native JSONL — all editable locally.

*No telemetry or automatic cloud connection. Solo mode needs no account.*

## Features

- 🖼️ **Boxes, polygons, and multi-label classification** with a native-painted canvas
- **Home screen** with recent projects, Continue, and four pipeline presets
- **White and black themes** with persistent preferences and focus mode
- **Separate workspaces**: classification-only projects show classes, detection shows boxes, segmentation shows polygons
- **Team mode**: optional host service, reviewer tokens, background synchronization, revision conflicts, revocation, and saved-version audit history
- 💾 **Offline SQLite projects** with versioned migrations, WAL, and transactional saves
- 🛟 **Recovery drafts** — every edit is written to a recovery draft; autosave debounces 700 ms
- 🎛️ **Normalized geometry** (0–1) so coordinates survive resolution changes and re-linking
- ⏩ **Headless CLI** — `lannotex export` and `lannotex analyze` for CI and automation
- 📦 **Export formats**: Labelme JSON, YOLO boxes, COCO JSON, Classification CSV, Native JSONL
- 🔄 **Undo / redo** (100 steps), zoom-under-pointer, pan, and arrow-key nudging
- 🚀 **Virtualized image list** — only 8 pages × 128 records in memory, no matter the dataset size
- 🔒 **Solo works offline** — network connections occur only when you host or join a team

## Install

Requires **Python 3.11+**. Lannotex runs on Windows, macOS, and Linux.

### From PyPI

```bash
# pip
python -m pip install lannotex
lannotex

# uv
uv tool install lannotex
lannotex
```

### Standalone binaries

Grab the prebuilt executable for your OS from the
[Releases](https://github.com/Lourdhu02/Lannotex/releases) page. Binaries run without a
separate Python install. The app stores project files only in the project directory — it
never writes project data into its installation directory.

### From source

```bash
git clone https://github.com/Lourdhu02/Lannotex.git
cd Lannotex
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev]
lannotex
```

## Quick start

1. **New project** — name it, choose a location, pipeline, and Solo or Team mode. Or **Continue** from Home.
2. **Import folder / files** — add JPEG, PNG, or WebP images. Nothing is moved or copied.
3. **Add classes or object labels**. Classification uses checkboxes; detection and segmentation expose only their drawing tools.
4. **Save** (`Ctrl+S`) or **Save & next** (`Ctrl+Enter`).

> Projects keep image references relative to the project folder in this release. If you move
> an image, choose **Project → Relink current image** to point at its new location.

## Command line

```bash
lannotex                      # launch the desktop app
lannotex gui --smoke-test     # bounded Qt event-loop test (for CI)
lannotex new ./dataset        # create an empty project
lannotex analyze ./dataset    # JSON validation report
lannotex export ./dataset ./out --format "YOLO boxes"
lannotex invite ./dataset "Reviewer name"  # prints a private reviewer token once
lannotex host ./dataset --bind 0.0.0.0 --port 8765
```

`export` accepts: `Labelme JSON`, `YOLO boxes`, `COCO JSON`, `Classification CSV`,
`Native JSONL`.

## Keyboard & controls

| Keys | Action |
| --- | --- |
| `B` / `P` / `V` | Box / polygon / select tool |
| `Enter` | Finish polygon |
| `Escape` | Cancel drawing |
| `Delete` | Delete selection · `Shift+Del` deletes a polygon vertex |
| `R` | Redraw the selected annotation in place |
| `F` | Fit image |
| `Space + drag` | Pan · wheel zooms under the pointer |
| `Ctrl+Z` / `Ctrl+Shift+Z` | Undo / redo |
| `Ctrl+S` / `Ctrl+Enter` | Save / Save & next |
| Arrow keys | Nudge selection (`Shift` = 10× step) |

All shortcuts are remappable under **Help → Keyboard & preferences**.

## Privacy

Solo mode references local images and makes no network requests. Team mode connects
only to the host address you enter. Images are downloaded on demand, and annotations
sync in the background. Reviewer tokens are retained only in memory on the client;
the host stores token hashes. There is no telemetry, external AI, or automatic upload
to a company service. See [the team guide](docs/TEAM.md) for trusted-LAN/TLS setup,
conflict resolution, and the limits of the current collaboration model.

## Architecture

```
src/lannotex/
├── domain.py       # normalized annotation model, geometry validation, undo/redo document
├── storage.py      # SQLite schema + migrations, drafts, transactional writes, backup/restore
├── exporters.py    # Labelme / YOLO / COCO / CSV / JSONL export + import + analysis
├── canvas.py       # native Qt canvas: draw, select, edit, pan, zoom
├── app.py          # main window, menus, dialogs, background job orchestration
├── home.py         # home / recents and pipeline project creation
├── team.py         # authenticated host, client outbox and conflict resolution
├── models.py       # virtualized image list model (8-page cache)
├── workers.py      # cancellable jobs + bounded serial image decoder (96 MB cache)
├── theme.py        # dark / light theme
└── cli.py          # headless command-line interface
```

## Roadmap

Current verification and measured limits are in [docs/VERIFICATION.md](docs/VERIFICATION.md)
and [docs/PERFORMANCE.md](docs/PERFORMANCE.md). Team hosting is intended for a trusted
LAN/VPN (or CLI-configured TLS). Multi-stage independent review/adjudication, hosted
internet deployment, and clean-VM certification are not claimed by this release.

## Contributing

Contributions are welcome! Start with [CONTRIBUTING.md](CONTRIBUTING.md) and our
[Code of Conduct](CODE_OF_CONDUCT.md). Please report bugs through
[GitHub Issues](https://github.com/Lourdhu02/Lannotex/issues).

## License

[MIT](LICENSE) © Lannotex contributors. Third-party licenses are listed in
[LICENSES/THIRD_PARTY_NOTICES.md](LICENSES/THIRD_PARTY_NOTICES.md).
