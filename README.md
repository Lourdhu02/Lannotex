<div align="center">

<img src="https://raw.githubusercontent.com/Lourdhu02/Lannotex/main/docs/assets/logo.svg" width="88" alt="Lannotex logo">

# Lannotex

**Fast, offline-first image annotation for bounding boxes, polygons, and image classes.**<br>
Free and MIT-licensed. LabelMe-compatible. Your images never leave your machine.

[![CI](https://img.shields.io/github/actions/workflow/status/Lourdhu02/Lannotex/ci.yml?branch=main&label=tests)](https://github.com/Lourdhu02/Lannotex/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/github/actions/workflow/status/Lourdhu02/Lannotex/docs.yml?branch=main&label=docs)](https://lourdhu02.github.io/Lannotex/)
[![Python](https://img.shields.io/badge/python-3.11%20%E2%80%93%203.14-3776ab)](https://lourdhu02.github.io/Lannotex/getting-started/installation/)
[![Platforms](https://img.shields.io/badge/Windows%20%C2%B7%20macOS%20%C2%B7%20Linux-supported-555)](https://github.com/Lourdhu02/Lannotex/releases)
[![License: MIT](https://img.shields.io/github/license/Lourdhu02/Lannotex?color=37b8a5)](https://github.com/Lourdhu02/Lannotex/blob/main/LICENSE)

[**Documentation**](https://lourdhu02.github.io/Lannotex/) ·
[Quick start](https://lourdhu02.github.io/Lannotex/getting-started/quickstart/) ·
[Coming from LabelMe](https://lourdhu02.github.io/Lannotex/migrate-from-labelme/) ·
[Releases](https://github.com/Lourdhu02/Lannotex/releases)

<img src="https://raw.githubusercontent.com/Lourdhu02/Lannotex/main/docs/assets/demo.gif" width="860" alt="Drawing two boxes and a polygon on a cat photo in Lannotex, then saving and moving to the next image">

</div>

## Why Lannotex?

- **Everything you need is free.** YOLO, COCO, Labelme and CSV export, standalone desktop builds, and team review are all free and open source. No license keys, no Pro tier.
- **Built for real datasets.** A project is one SQLite file instead of thousands of JSON files. The image list is virtualized, so its memory use stays flat; it was [benchmarked](https://lourdhu02.github.io/Lannotex/PERFORMANCE/) at 100,000 records. Your source images are never moved or modified.
- **You can't lose work.** Every edit is written to a recovery draft, saves are transactional, and broken geometry (self-intersecting polygons, zero-size boxes) is rejected before it reaches your dataset.
- **Private by default.** No account, no telemetry, no cloud. The app makes network requests only if you choose to host or join a team on your own network.

## Install

```bash
uv tool install lannotex   # recommended, isolated install
lannotex
```

<details>
<summary>pip, pipx, standalone builds, and source</summary>

```bash
pipx install lannotex
# or, inside a virtual environment
python -m pip install lannotex
```

**Standalone builds** for Windows, macOS, and Linux are attached to every
[release](https://github.com/Lourdhu02/Lannotex/releases). They bundle Python and Qt, so
nothing else is needed.

**From source:**

```bash
git clone https://github.com/Lourdhu02/Lannotex.git && cd Lannotex
uv venv && uv pip install -e ".[dev]"
lannotex
```

</details>

Lannotex supports Python 3.11–3.14 on Windows, macOS, and Linux. See the
[installation guide](https://lourdhu02.github.io/Lannotex/getting-started/installation/)
for details.

## Your first dataset in 60 seconds

1. **Create a project** and pick a pipeline: *Classification*, *Object detection*, *Segmentation*, or *Combined*. Each one shows only the tools it needs.
2. **Import a folder** (`Ctrl+I`). JPEG, PNG and WebP files are checked and referenced in place, not copied.
3. **Add labels**, then draw: `B` for boxes, `P` for polygons (`Enter` finishes), `V` to select and edit.
4. **Save & next** with `Ctrl+Enter`. Autosave and recovery drafts run in the background anyway.
5. **Export** to the format your training code expects.

Every shortcut can be remapped. See the [annotating guide](https://lourdhu02.github.io/Lannotex/guide/annotating/) for the full list.

<table>
  <tr>
    <td><img src="https://raw.githubusercontent.com/Lourdhu02/Lannotex/main/docs/assets/workspace-light.png" alt="Lannotex workspace in light theme with a polygon and a box on a coffee cup"></td>
    <td><img src="https://raw.githubusercontent.com/Lourdhu02/Lannotex/main/docs/assets/workspace-dark.png" alt="Lannotex workspace in dark theme with boxes on an astronaut photo"></td>
  </tr>
  <tr>
    <td align="center">Light theme · polygon vertex editing</td>
    <td align="center">Dark theme · object detection</td>
  </tr>
</table>

## Features

| | |
| --- | --- |
| **Annotate** | Bounding boxes · polygons with vertex drag, insert, and delete · multi-label image classes · "no target" negatives · 100-step undo/redo · zoom under the pointer, pan, arrow-key nudging · focus mode · light and dark themes |
| **View** | Sharp full-resolution zoom up to 6400% · next/previous images decoded ahead · minimap · pixel grid · brightness, contrast and gamma · thumbnails · dockable panels you can float onto a second monitor, with saved layouts · `Ctrl+K` command palette |
| **Stay safe** | SQLite projects with versioned migrations · recovery drafts and 700 ms autosave · transactional saves · geometry validation · backup and restore · relinking for moved images · EXIF orientation handled |
| **Scale** | Virtualized image list (at most 1,024 records in memory) · background import and decoding · 96 MB preview cache · coordinates normalized to the original resolution |
| **Export** | Labelme JSON · ready-to-train YOLO (`images/`, `labels/`, `data.yaml`) · COCO JSON · classification CSV · lossless native JSONL · each export reports anything it skipped |
| **Automate** | `lannotex export` and `lannotex analyze` run headless in CI, with no display needed |
| **Collaborate** | Optional LAN host with per-reviewer tokens, background sync, revision conflicts you resolve explicitly, revocation, and an audit history |

## Lannotex vs. LabelMe

LabelMe is a great tool and Lannotex reads and writes its JSON format, so you can switch
without converting anything.

| | Lannotex | LabelMe |
| --- | :---: | :---: |
| License | MIT | GPL-3.0 |
| Standalone desktop app | Free | Paid license |
| YOLO export | ✅ Free | Pro tier |
| COCO export | ✅ | ✅ |
| One database per dataset | ✅ | One JSON per image |
| Crash recovery and transactional saves | ✅ | Optional autosave |
| Team review with conflict handling | ✅ | — |
| Headless export and validation CLI | ✅ | Example scripts |
| AI-assisted annotation (SAM) | Not yet | ✅ |
| Circles, lines, points, rotated boxes | Not yet | ✅ |

Based on LabelMe's published features and pricing as of October 2026. The
[full comparison and migration guide](https://lourdhu02.github.io/Lannotex/migrate-from-labelme/)
covers which LabelMe shapes import today.

## Command line

```bash
lannotex new ./dataset                                  # create a project
lannotex analyze ./dataset                              # JSON health report: counts, problems, drafts
lannotex export ./dataset ./out --format "COCO JSON"    # Labelme JSON | YOLO boxes | COCO JSON | Classification CSV | Native JSONL
lannotex invite ./dataset "Alice"                       # print a one-time reviewer token
lannotex host ./dataset --bind 0.0.0.0 --port 8765      # share a project on your LAN (TLS via --cert/--key)
```

`analyze` writes clean JSON to stdout, so it can gate a training pipeline. See the
[CLI reference](https://lourdhu02.github.io/Lannotex/cli/).

## Privacy

Solo projects make no network requests. Team mode connects only to the host address you
enter, reviewer tokens are kept in memory on clients, and the host stores only token
hashes. There is no telemetry, no external AI service, and no automatic upload. Read the
[team guide](https://lourdhu02.github.io/Lannotex/TEAM/) for LAN and TLS setup.

## Roadmap

Next up: point, line, rotated-box, keypoint and brush-mask tools, per-object attributes,
and VOC, YOLO-seg and YOLO-OBB export. See the
[roadmap](https://lourdhu02.github.io/Lannotex/ROADMAP/) and the
[measured performance](https://lourdhu02.github.io/Lannotex/PERFORMANCE/).

## Contributing

Bug reports, ideas, and pull requests are welcome. Start with
[CONTRIBUTING.md](https://github.com/Lourdhu02/Lannotex/blob/main/CONTRIBUTING.md), and
please follow the [Code of Conduct](https://github.com/Lourdhu02/Lannotex/blob/main/CODE_OF_CONDUCT.md).
Report security issues privately, as described in
[SECURITY.md](https://github.com/Lourdhu02/Lannotex/blob/main/SECURITY.md).

If Lannotex saves you time, a ⭐ helps other people find it.

## License

[MIT](https://github.com/Lourdhu02/Lannotex/blob/main/LICENSE) © 2026 [Lourdhu Raju](https://github.com/Lourdhu02). Third-party licenses are
listed in [THIRD_PARTY_NOTICES.md](https://github.com/Lourdhu02/Lannotex/blob/main/LICENSES/THIRD_PARTY_NOTICES.md).
Demo images are public-domain and CC0 samples from
[scikit-image](https://scikit-image.org/docs/stable/api/skimage.data.html).
