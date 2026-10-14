# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
