# Roadmap

This document captures work beyond the current desktop refresh. Home, pipeline
presets, monochrome themes, background imports, editable polygons, analysis,
backup/restore/relink, and optional team synchronization are implemented. Their
tested scope is documented in VERIFICATION.md.

## v0.1 — dataset-scale reliability

- **Dataset validation and thumbnail strip** — measure real 10 GB datasets;
  add lazily generated thumbnails to the paged list.
- **Tiled, full-resolution zoom** — avoid full-size transient decode memory and
  preview-resolution limits on extremely large images.
- **Project archive / restore / relink UI** — one-click archive of images +
  annotations, and bulk re-linking of moved folders.
- **Undo/redo across navigation** — persist the undo stack with drafts so
  history survives image switches and restarts.

## v0.2 — export & automation

- **Export wizard** with format previews and per-format options.
- **Team assignments and independent review** — optional work allocation,
  review roles, and a visual saved-version comparison screen.
- **Network soak tests** — real multi-computer LAN, host sleep, reconnect, TLS,
  and high-volume conflicts.
- **Python API documentation** for `domain`, `storage`, and `exporters` so
  Lannotex can be embedded in training pipelines.

## v0.3 — distribution & ecosystem

- **Microsoft Store packaging** (MSIX, explicit capability review for optional team hosting).
- **Auto-update channel** for standalone binaries.
- **npm companion CLI** *(optional)* — a thin JS/TS shim that downloads the
  prebuilt binary for each platform, for teams that standardize on Node tooling.
- **Plugin hooks** for custom export formats and label sources.

## Principles

- Local projects and exports remain fully usable without any entitlement or
  cloud service; paid/future desktop features, if any, must be strictly optional.
- Image data is never altered; annotation geometry stays normalized so it
  survives resolution changes.
