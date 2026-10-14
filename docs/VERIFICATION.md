# Verification — desktop workflow refresh

Validated on Windows 11 build 26300, Python 3.11.9, PySide6 6.8.3, Pillow 11.1.0.
Source version remains 0.0.2, preserving the Lannotex rebrand and existing repository
metadata. No packages, commits, releases, or visibility changes were published.

Tests cover geometry, invalid saves, transaction rollback, migrations, backup/restore
and relocated references, recovery drafts, import damage reporting, all five export
formats, native round trips, CLI parsing, and real Qt interactions. GUI tests create
isolated temporary projects/settings: no fixture images or profiles are installed as
application data.

Final regression run: **42 tests passed**; Ruff checks passed. The Windows executable
was built in a fresh isolated `.venv-build` with pinned runtime/build dependencies.
The packaged test launches from a temporary working directory without `PYTHONPATH`,
waits for process exit, and requires a written receipt confirming a visible window
and a completed Qt event loop. This does not substitute for a clean Windows VM test.
The final packaged check completed in 1.987 seconds including the 300 ms test timer
and shutdown; this is process-to-exit timing, not a standalone cold-start benchmark.

Native Qt checks exercise Home, both monochrome palettes, classification-only controls,
box drawing/moving, undo then immediate save, polygon reopening/redraw cancellation,
failed-save navigation protection, text-entry shortcut isolation and window resizing.
The client UI also downloads a host image, edits it, saves and synchronizes it to the
host. Two independent HTTP clients are tested against a real loopback server for
simultaneous saves, stale revisions, revocation, invalid geometry, disabled pipelines,
private cache/outbox conflicts, resolution, downloads and preservation of owner drafts.

Limits of this verification:

- Two client connections were run on one machine. Real LAN routing, Windows firewall
  rules, host sleep/reconnect, bandwidth and cross-machine latency need testing on the
  user's network.
- No fresh Windows VM, macOS or Linux run was available in this session.
- Display images are capped at 2560 px. Normalized coordinates and exports retain
  original dimensions; pixel-perfect deep zoom beyond the preview needs a future tiled decoder.
- Metadata caches are bounded; decoding one enormous PNG/WebP can still require a
  full-size transient image. Pillow's image-size safeguards remain enabled.
- Host members can review the whole project. Assignment/review/adjudication roles from
  the company LabelReview product are not implemented in this desktop refresh.
- Saved history is stored in SQLite; a full visual version-comparison UI is future work.

Reproduce: `python -m pytest`, `python -m ruff check src tests scripts`,
`python scripts/benchmark.py`, and `powershell -File scripts/build_windows.ps1`.
