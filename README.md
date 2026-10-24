<div align="center">

<img src="https://raw.githubusercontent.com/Lourdhu02/Lannotex/main/docs/assets/logo.svg" width="88" alt="Lannotex logo">

# Lannotex

**The image annotation tool that doesn't slow down, doesn't phone home, and doesn't charge you.**<br>
Boxes, polygons and classes · any image size · offline by default · MIT.

[![CI](https://img.shields.io/github/actions/workflow/status/Lourdhu02/Lannotex/ci.yml?branch=main&label=tests)](https://github.com/Lourdhu02/Lannotex/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/github/actions/workflow/status/Lourdhu02/Lannotex/docs.yml?branch=main&label=docs)](https://lourdhu02.github.io/Lannotex/)
[![PyPI](https://img.shields.io/pypi/v/lannotex?color=37b8a5)](https://pypi.org/project/lannotex/)
[![Python](https://img.shields.io/badge/python-3.11%20%E2%80%93%203.14-3776ab)](https://lourdhu02.github.io/Lannotex/getting-started/installation/)
[![Platforms](https://img.shields.io/badge/Windows%20%C2%B7%20macOS%20%C2%B7%20Linux-supported-555)](https://github.com/Lourdhu02/Lannotex/releases)
[![License: MIT](https://img.shields.io/github/license/Lourdhu02/Lannotex?color=37b8a5)](https://github.com/Lourdhu02/Lannotex/blob/main/LICENSE)

[**Documentation**](https://lourdhu02.github.io/Lannotex/) ·
[Quick start](https://lourdhu02.github.io/Lannotex/getting-started/quickstart/) ·
[Coming from LabelMe](https://lourdhu02.github.io/Lannotex/migrate-from-labelme/) ·
[Troubleshooting](https://lourdhu02.github.io/Lannotex/guide/troubleshooting/) ·
[Releases](https://github.com/Lourdhu02/Lannotex/releases)

<img src="https://raw.githubusercontent.com/Lourdhu02/Lannotex/main/docs/assets/demo.gif" width="860" alt="Drawing two boxes and a polygon over a sailing photo in Lannotex, then saving and moving to the next image">

</div>

Lannotex is a desktop app for labelling images to train computer-vision models. It keeps your
dataset in a single SQLite file on your disk, exports to the formats training code actually
wants, and stays responsive on images and documents that make other tools crawl.

```bash
uv tool install lannotex && lannotex
```

## Why Lannotex

- **It stays quick on dense images.** Editing costs the shape you touched, not the size of the
  document. A 200-shape image used to freeze for six seconds on every mouse release; the same
  edit now takes **0.2 ms**. CI fails the build if an edit ever exceeds 16 ms.
- **Image size stops mattering.** Zoom past the preview and Lannotex builds a tile pyramid once
  and caches it. A **900 MP** TIFF reopens in **98 ms** using **196 MB** — decoding it whole
  would need 2.7 GB.
- **You can't lose work.** Every edit reaches a recovery draft within 250 ms, saves are
  transactional, and undo history survives a crash. Self-intersecting polygons and zero-area
  boxes are refused before they reach your dataset.
- **Everything is free, and private.** Every export format, the desktop builds and team review
  are MIT. No account, no telemetry, no licence keys, no Pro tier.

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

**Standalone builds** for Windows, macOS and Linux are attached to every
[release](https://github.com/Lourdhu02/Lannotex/releases). They bundle Python and Qt, so
nothing else is needed.

**From source:**

```bash
git clone https://github.com/Lourdhu02/Lannotex.git && cd Lannotex
uv venv && uv pip install -e ".[dev]"
lannotex
```

</details>

Lannotex supports Python 3.11–3.14 on Windows, macOS and Linux. See the
[installation guide](https://lourdhu02.github.io/Lannotex/getting-started/installation/)
for details.

## Your first dataset in 60 seconds

1. **Create a project** and pick a pipeline: *Classification*, *Object detection*,
   *Segmentation* or *Combined*. Each one shows only the tools it needs.
2. **Import a folder** (`Ctrl+I`). JPEG, PNG, WebP, TIFF and BMP files are checked and
   referenced in place, not copied.
3. **Add labels**, then draw: `B` for boxes, `P` for polygons (`Enter` finishes), `V` to select
   and edit.
4. **Save & next** with `Ctrl+Enter`. Autosave and recovery drafts run in the background anyway.
5. **Export** to the format your training code expects.

Every shortcut can be remapped. See the
[annotating guide](https://lourdhu02.github.io/Lannotex/guide/annotating/) for the full list.

<table>
  <tr>
    <td><img src="https://raw.githubusercontent.com/Lourdhu02/Lannotex/main/docs/assets/workspace-light.png" alt="Lannotex workspace in light theme, three boxes and a polygon over a sailing photo"></td>
    <td><img src="https://raw.githubusercontent.com/Lourdhu02/Lannotex/main/docs/assets/workspace-dark.png" alt="Lannotex workspace in dark theme, a polygon around a swimming pool and boxes on sun loungers"></td>
  </tr>
  <tr>
    <td align="center">Light theme · boxes and a polygon</td>
    <td align="center">Dark theme · segmentation</td>
  </tr>
</table>

## Export to what your model expects

```bash
lannotex export ./dataset ./out --format "YOLO boxes" --split
```

```
out/Lannotex-export-ff6e2f7f/
├── data.yaml                # path, train/val/test sets, class names — ready for `yolo train`
├── classes.json
├── manifest.json            # what was exported, and anything skipped
├── images/{train,val,test}/
└── labels/{train,val,test}/
    └── 00000001_boats.txt   # 4 0.400566 0.533165 0.149150 0.441646
```

The split is derived from a hash of each filename, so it is reproducible and stable as the
dataset grows. Every export reports what it skipped and why, instead of silently dropping it.

Also exports **Pascal VOC**, **COCO JSON**, **YOLO segments**, **LabelMe JSON**,
**classification CSV** and **lossless native JSONL** — and imports COCO, YOLO, VOC, LabelMe and
native JSONL, detected from whatever you point at.

## What you get

<details open>
<summary><b>Annotate</b></summary>

Bounding boxes · polygons with vertex drag, insert and delete · multi-label image classes ·
"no target" negatives · 100-step undo/redo · number keys 1–9 to pick a label · zoom under the
pointer, pan and arrow-key nudging · focus mode · light and dark themes.

</details>

<details>
<summary><b>View any image size</b></summary>

A 900 MP TIFF reopens in 98 ms and pans from a cached tile pyramid using 196 MB · sharp
full-resolution zoom to 6400% · next and previous images decoded ahead · minimap · pixel grid ·
brightness, contrast and gamma · thumbnails · dockable panels you can float onto a second
monitor, with saved layouts · `Ctrl+K` command palette.

</details>

<details>
<summary><b>Keep your work safe</b></summary>

SQLite projects with versioned, append-only migrations · recovery drafts written every 250 ms ·
undo history that survives a crash · transactional saves · geometry validation · backup and
restore · relinking for moved images · EXIF orientation handled.

</details>

<details>
<summary><b>Scale and automate</b></summary>

Edits cost the shape you touched, not the document: 0.2 ms on a 200-shape image, gated at 16 ms
in CI · virtualized image list (at most 1,024 records in memory) · background import, decoding
and tiling · coordinates normalized to the original resolution · `lannotex export`, `import`
and `analyze` run headless in CI with no display.

</details>

<details>
<summary><b>Review as a team</b></summary>

Optional LAN host with per-reviewer tokens, background sync, revision conflicts you resolve
explicitly, revocation, and an audit history. No server account and nothing leaves your network.

</details>

## Measured, not claimed

Every number here comes from a script in [`scripts/bench/`](scripts/bench) that you can run
yourself. Hardware: AMD Ryzen 9 8940HX, 23 GiB RAM, Windows 11, Python 3.12.

| On a 200-shape image | Before | Now |
| --- | ---: | ---: |
| Validate the document | 4,833 ms | **0.115 ms** |
| Move a shape | 108 ms | **0.192 ms** |
| Undo | 30.5 ms | **0.033 ms** |
| Save annotations | 4,986 ms | **13.8 ms** |

| On a 900 MP (30,000 × 30,000) TIFF | |
| --- | ---: |
| Reopen | **98 ms** |
| Pan at 100% zoom, p50 | **10.3 ms** |
| Memory while viewing | **196 MB** |

The [performance page](https://lourdhu02.github.io/Lannotex/PERFORMANCE/) has the full tables,
the method, and an honest list of what is **not** fast yet — a first-ever open of a 900 MP TIFF
still costs 2.8 s, because Pillow cannot decode part of one.

## Lannotex vs. LabelMe

LabelMe is a good tool, and Lannotex reads and writes its JSON format, so you can switch
without converting anything.

| | Lannotex | LabelMe |
| --- | :---: | :---: |
| License | MIT | GPL-3.0 |
| Standalone desktop app | Free | Paid licence |
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

## Is this for you?

**A good fit if** you label datasets on your own machine, care about keeping data off other
people's servers, work with large or dense images, or want the whole toolchain under a
permissive licence.

**Not yet, if** you need AI-assisted segmentation such as SAM, or shapes beyond boxes and
polygons — points, lines, circles, rotated boxes and keypoints are on the
[roadmap](https://lourdhu02.github.io/Lannotex/ROADMAP/) but not here today. Lannotex is also a
desktop app, not a hosted labelling service with a managed workforce.

## Command line

```bash
lannotex new ./dataset                                  # create a project
lannotex analyze ./dataset                              # JSON health report: counts, problems, drafts
lannotex export ./dataset ./out --format "YOLO boxes" --split
lannotex invite ./dataset "Alice"                       # print a one-time reviewer token
lannotex host ./dataset --bind 0.0.0.0 --port 8765      # share a project on your LAN (TLS via --cert/--key)
```

`analyze` writes clean JSON to stdout, so it can gate a training pipeline. See the
[CLI reference](https://lourdhu02.github.io/Lannotex/cli/).

## Privacy

Solo projects make no network requests at all. Team mode connects only to the host address you
type in, reviewer tokens stay in memory on clients, and the host stores only token hashes.
There is no telemetry, no external AI service and no automatic upload. The
[team guide](https://lourdhu02.github.io/Lannotex/TEAM/) covers LAN and TLS setup.

## Contributing

Bug reports, ideas and pull requests are welcome. Start with
[CONTRIBUTING.md](https://github.com/Lourdhu02/Lannotex/blob/main/CONTRIBUTING.md), and please
follow the [Code of Conduct](https://github.com/Lourdhu02/Lannotex/blob/main/CODE_OF_CONDUCT.md).
Report security issues privately, as described in
[SECURITY.md](https://github.com/Lourdhu02/Lannotex/blob/main/SECURITY.md).

If Lannotex saves you time, a ⭐ helps other people find it.

## License

[MIT](https://github.com/Lourdhu02/Lannotex/blob/main/LICENSE) © 2026
[Lourdhu Raju](https://github.com/Lourdhu02). Third-party licences are listed in
[THIRD_PARTY_NOTICES.md](https://github.com/Lourdhu02/Lannotex/blob/main/LICENSES/THIRD_PARTY_NOTICES.md),
and the photographs in the screenshots are credited in
[docs/assets/CREDITS.md](https://github.com/Lourdhu02/Lannotex/blob/main/docs/assets/CREDITS.md).
