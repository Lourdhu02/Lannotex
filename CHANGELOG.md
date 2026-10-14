# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.2] — 2026-10-14

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

## [0.0.1] — 2026-10-14

- Initial offline PySide6 desktop application.
- SQLite project persistence with an explicit migration table and transactional annotation saves.
- Folder import for JPEG, PNG, and WebP; normalized box and polygon annotations.
- Labelme, YOLO and COCO conversion primitives plus geometry/persistence tests.
