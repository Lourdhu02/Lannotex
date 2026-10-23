# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Images of any size.** Zooming past the preview now builds a tile pyramid once, caches it on
  disk, and draws only the tiles on screen. A 900 MP TIFF reopens in 0.1 s, pans at roughly
  100 fps and uses under 200 MB — the whole image would need 2.7 GB to decode. The old 64 MP
  limit on full-resolution viewing is gone. Numbers and the remaining cold-open cost are in
  [docs/PERFORMANCE.md](docs/PERFORMANCE.md).
- **TIFF, BigTIFF and BMP** can be imported, alongside JPEG, PNG and WebP.
- **16-bit and floating-point images** are displayed by stretching their actual range, instead
  of clipping almost everything to black or white.

### Changed

- **Dense images are no longer slow to edit.** A 200-shape image used to freeze for about six
  seconds on every mouse release; the same edit now takes 0.2 ms. Moving a shape is 563×
  faster, undo 923×, saving 361×, and validating the document 42,000×. Measurements, method
  and the remaining costs are in [docs/PERFORMANCE.md](docs/PERFORMANCE.md).
  - Polygon self-intersection sweeps the x axis instead of testing every pair of edges.
  - Validation results and annotation JSON are reused for shapes that did not change.
  - Undo records what changed rather than copying the whole document.
  - The canvas reuses screen polygons and skips shapes outside the view or the click.
- **Undo history survives a crash.** It is written alongside the recovery draft, so reopening a
  project with unsaved work restores the undo stack too.
- **Recovery drafts are written at most once every 250 ms** instead of on every edit, and on
  navigation, save and close. They remain crash-safe: a test kills the process mid-edit and
  reopens the draft.
- Team hosting no longer re-runs schema migrations, under an exclusive lock, on every request.

### Added

- `scripts/bench/interaction.py` measures interaction latency and fails CI when the p95 for an
  edit exceeds 16 ms or a draft write exceeds 50 ms.
- Property-based tests (hypothesis) assert the fast self-intersection sweep always agrees with
  the original pairwise implementation, which is kept as `polygon_self_intersects_pairwise`.

### Migrations

- **6** adds indexed `label` and `kind` columns to `annotations`, backfilled from existing JSON,
  and a `history` column to `drafts`. Renaming or removing a label is now a single SQL
  statement. Projects from 0.2.0 upgrade on open; a test covers that path.

## [0.2.0] — 2026-10-14

Viewing, speed and layout: sharp zoom on large images, instant navigation, and a
workspace you can arrange yourself.

### Added

- **Full-resolution viewing.** Zooming in past the preview loads the original pixels in the
  background, so large images stay sharp at any zoom. Only the visible region is drawn.
  Detail decoding is capped at 64 MP to protect memory.
- **Instant next/previous.** Neighbouring images are decoded ahead of time.
- **Minimap** (`M`) for orientation and click-to-jump, and a **pixel grid** (`G`) from
  1200% zoom upwards.
- **Zoom controls:** actual pixels (`Ctrl+1`), zoom in/out (`Ctrl+=` / `Ctrl+-`) up to
  6400%. The zoom readout now shows true pixel scale, so 100% means actual pixels.
- **Image adjustments:** brightness, contrast and gamma in a new **Image view** panel. They
  change the display only, never your files, and are applied just to the visible region, so
  they stay fast on large images.
- **Dockable panels:** Dataset, Inspector and Image view can be moved, tabbed, floated onto
  another monitor, or closed. Your layout is remembered between sessions. Use
  **View → Panels** to bring a panel back or apply a preset (default, or all panels on the
  right). Focus mode hides every panel and restores your exact layout afterwards.
- **Thumbnails in the image list**, generated in the background with the rows you can see
  first. They're cached on disk in your user cache folder, not the project, so reopening a
  project is instant. The cache is capped at 512 MB. Toggle them under **View → Show
  thumbnails in image list**.
- **Icons:** a consistent line-icon set for the toolbar, navigation and Home screen,
  redrawn for light and dark themes, plus the Lannotex logo as the window icon. Icon-only
  buttons have tooltips and screen-reader names.
- **Command palette** (`Ctrl+K`): type part of any menu command, for example "zoom",
  "export" or "layout", and press Enter to run it.
- **Number keys 1–9** choose the drawing label, which relabels the selected shape, or
  toggle classes in classification projects.
- **Project → Import LabelMe folder…** imports a whole folder, including subfolders.

### Changed

- **LabelMe import keeps going.**
  - Circles and rotated rectangles are converted to polygons.
  - Points, lines and masks, which Lannotex can't draw yet, are skipped and counted in the
    import summary instead of rejecting the whole file.
  - Invalid shapes are dropped one at a time.
  - A malformed JSON file no longer stops the rest of the folder.

### Fixed

- PySide6 6.12.0 is excluded. On Linux with Python 3.11 it over-releases references on every
  background job, which made Lannotex abort on exit. Versions 6.8.3–6.11 are unaffected.

## [0.1.1] — 2026-10-14

### Changed

- **YOLO export is ready to train with Ultralytics:** `images/` (hard-linked when
  possible, otherwise copied), matching `labels/`, and a `data.yaml` with class names.
  Images that haven't been annotated yet are left out, so they don't become false
  negatives.

## [0.1.0] — 2026-10-14

First public release on PyPI: `pip install lannotex` or `uv tool install lannotex`.
Standalone builds for Windows, macOS, and Linux are attached to the GitHub release.

### Added

- Documentation site (MkDocs Material) with install, quick start, user guide, CLI
  reference, and a LabelMe migration guide; deployed to GitHub Pages.
- Issue forms, pull request template, Dependabot, and `CITATION.cff`.

### Fixed

- `pip install` / `uv tool install` failed on Python 3.14: runtime dependencies are now
  ranges (`PySide6-Essentials>=6.8.3,<7`, `Pillow>=11.1`) instead of exact pins. The
  smaller `PySide6-Essentials` replaces the full `PySide6` bundle.
- Buttons and menus showed "Save  next" and "Keyboard  preferences": `&` is now escaped.
- Test runs added temporary folders to the real recent-projects list. Settings are now
  stored in an INI file, so tests can isolate them. Earlier preferences are not migrated.
- Fonts follow the operating system instead of a hard-coded Segoe UI.
- The class list no longer clips rows on newer Qt versions.
- Version strings in exports, the team server, and window titles come from one place.

### Changed

- CI tests Python 3.11–3.14 and checks a `uv tool install` on every OS.

## [0.0.2] — 2026-10-14

### Desktop workflow refresh (local working tree)

- Home screen with Create, Continue, recent projects, and explicit pipeline presets.
- Monochrome white/black themes; classification, detection and segmentation expose only relevant controls.
- Optional simultaneous team collaboration: host service, reviewer access tokens, revocation, local outbox, incremental sync, conflict resolution, and saved annotation history.
- Forward migrations for revision and reviewer data; stale saves cannot silently replace newer work.
- Native Qt interaction and two-client integration tests, including failed writes, PNG imports, all export formats, and native round trips.
- Fixed PNG validation after EXIF inspection, trigger-inflated import counts, and backup relocation of relative image references.
- Added reproducible image-import, decode, metadata-cache and memory benchmark.

### Added

- Project renamed **LabelReview → Lannotex** across the codebase, packaging,
  exports, and documentation (`lannotex` PyPI package, `lannotex` console
  script, `Lannotex.spec`, `src/lannotex/`).
- Real command-line interface (`lannotex` / `python -m lannotex`):
  - `lannotex` — launch the desktop app (default)
  - `lannotex gui --smoke-test` — bounded Qt event-loop smoke test
  - `lannotex export <project> <dest> [--format ...]` — headless export
  - `lannotex analyze <project>` — headless validation report as JSON
  - `lannotex new <folder>` — create an empty project
- Cross-platform distribution story:
  - `scripts/build_macos.sh` and `scripts/build_linux.sh` alongside the Windows
    PowerShell build.
  - GitHub Actions CI (`ci.yml`) running tests on Windows/macOS/Linux ×
    Python 3.11/3.12.
  - GitHub Actions release workflow building and attaching PyInstaller
    artifacts for all three operating systems on tags.
- PyPI publishing metadata: classifiers, keywords, license file, project URLs,
  and a `MANIFEST.in` for complete sdists.
- Ruff linting (pyflakes + syntax errors) wired into `pyproject.toml` and CI.
- Community files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, and
  `docs/ROADMAP.md`.

### Changed

- Export metadata renamed from `labelreview`/`labelreview_id` to
  `lannotex`/`lannotex_id`; import still accepts the legacy `labelreview`
  keys so old Labelme files keep working.
- Window/brand strings, QSettings organization, and the smoke-test
  environment variable now use `Lannotex`/`LANNOTEX_SMOKE_RESULT`.
- Expanded test coverage (see `tests/`) for domain, storage, exporters, and CLI.

### Fixed

- `LICENSE` now contains the MIT text that `pyproject.toml` and the README
  declare (the file previously held the Boost Software License 1.0).
- Repository URLs, badges, and clone instructions now point at the real
  `Lourdhu02/Lannotex` remote instead of a non-existent `Lannotex/Lannotex`.
- Removed the broken `docs/screenshot.png` reference from the README.
- Security and conduct reports now use GitHub channels instead of the
  placeholder `@lannotex.dev` addresses.
- The release workflow only publishes to PyPI on a manual dispatch with
  `publish` enabled; tag pushes build and attach binaries only.

## [0.0.1] — 2026-10-14

- Initial offline PySide6 desktop application.
- SQLite project persistence with an explicit migration table and transactional annotation saves.
- Folder import for JPEG, PNG, and WebP; normalized box and polygon annotations.
- Labelme, YOLO and COCO conversion primitives plus geometry/persistence tests.
