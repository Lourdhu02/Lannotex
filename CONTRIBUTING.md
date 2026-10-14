# Contributing to Lannotex

Thanks for helping make Lannotex better! This project is local-first and
privacy-first — keep those values in mind in every change you make.

## Development setup

```bash
git clone https://github.com/Lannotex/Lannotex.git
cd Lannotex
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

## Commands

```bash
python -m pytest                 # run the test suite
python -m ruff check src tests   # lint (pyflakes + syntax errors)
lannotex gui --smoke-test        # bounded Qt event-loop smoke test
python -m build                  # build sdist + wheel
```

## Before you open a pull request

1. **Tests pass** — `python -m pytest` is green, including any new tests you add.
2. **Lint is clean** — `python -m ruff check src tests` reports nothing.
3. **Focused** — one logical change per PR, with a clear title and description.
4. **Documented** — user-visible changes are noted in `CHANGELOG.md`.

## Code conventions

- Python 3.11+, `from __future__ import annotations` at the top of modules.
- Keep geometry **normalized (0–1)** in the domain layer; convert only at export.
- Pure logic (domain, storage, exporters) must not import Qt so it stays testable
  and reusable headlessly.
- Follow the existing compact style; the ruff config intentionally tracks
  syntax errors (`E9`) and pyflakes (`F`) rather than fighting over formatting.

## Testing

New behavior should come with tests under `tests/`. Pure functions (geometry
validation, export primitives, storage) are the easiest and most valuable to cover;
UI interactions in `app.py`/`canvas.py` are covered via the smoke test.

## Reporting issues

- Include your OS, Python version, and Lannotex version (`lannotex --version`).
- For crashes, include the traceback and what you were doing.
- Remember: projects are just folders with a `project.sqlite3` — reproductions are easy.

## Code of conduct

All contributors must follow our [Code of Conduct](CODE_OF_CONDUCT.md).
