# Roadmap

This document captures where Lannotex is headed. v0.0.2 is the rebrand +
packaging + cross-platform release; the items below are the priority work to
make Lannotex a mature Labelme alternative.

## v0.1 — dataset-scale reliability

- **Background importer with a thumbnail cache** — replace the synchronous
  dimension read during folder import so 10 GB folders import in the background.
- **Polygon vertex editing reload rendering** — render saved polygons' vertices
  after reload (in-session editing already works).
- **Project archive / restore / relink UI** — one-click archive of images +
  annotations, and bulk re-linking of moved folders.
- **Undo/redo across navigation** — persist the undo stack with drafts so
  history survives image switches and restarts.

## v0.2 — export & automation

- **Export wizard** with format previews and per-format options.
- **Analysis page** in-app (today it is available via `lannotex analyze`).
- **Configurable themes and layout persistence** (today: dark/light + remembered
  window geometry).
- **Python API documentation** for `domain`, `storage`, and `exporters` so
  Lannotex can be embedded in training pipelines.

## v0.3 — distribution & ecosystem

- **Microsoft Store packaging** (MSIX, no network capability by default).
- **Auto-update channel** for standalone binaries.
- **npm companion CLI** *(optional)* — a thin JS/TS shim that downloads the
  prebuilt binary for each platform, for teams that standardize on Node tooling.
- **Plugin hooks** for custom export formats and label sources.

## Principles

- Local projects and exports remain fully usable without any entitlement or
  cloud service; paid/future desktop features, if any, must be strictly optional.
- Image data is never altered; annotation geometry stays normalized so it
  survives resolution changes.
