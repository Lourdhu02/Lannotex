# Architecture

How Lannotex is put together, for anyone changing it. The guiding constraint is that the parts
that own your data — geometry, storage, formats — know nothing about Qt, so they can be tested
headlessly and reused from the command line.

## The shape of it

```text
          ┌──────────── Qt, user-facing ────────────┐   ┌──── no Qt, testable headlessly ────┐

  home.py ──┐
  canvas.py ├─ app.py ──────────────────────────────────► domain.py   annotations, validation,
  widgets.py┤   the window: menus, panels, jobs           │            undo as deltas
  palette.py┘        │                                    │
                     ├──────────────────────────────────► storage.py  SQLite, migrations,
  tiles.py ◄─────────┤   tile pyramids, disk cache        │            drafts, transactions
  thumbnails.py ◄────┤   list thumbnails, disk cache      │
  workers.py ◄───────┘   decode and import, off the UI    ├─ exporters.py  write 7 formats
                                                          ├─ importers.py  read 5 formats
  team.py ──────────────────────────────────────────────► └─ cli.py        headless commands
      LAN host and client, HTTP + tokens
```

`cli.py` imports no Qt for its headless commands, so `lannotex export`, `import` and `analyze`
run on a server with no display.

## Modules

| Module | Holds |
| --- | --- |
| `domain.py` | `Annotation`, validation, the self-intersection sweep, and `Document` — the undo engine |
| `storage.py` | The SQLite schema, numbered migrations, recovery drafts, transactional saves, backup and restore |
| `exporters.py` | Labelme, YOLO boxes and segments, Pascal VOC, COCO, CSV, native JSONL, and `analyze` |
| `importers.py` | Format detection and readers for LabelMe, COCO, YOLO, VOC and native JSONL |
| `canvas.py` | Painting, hit-testing, zoom and pan. Geometry lives in the document, never in widgets |
| `tiles.py` | Tile pyramids and their disk cache, so image size stops mattering |
| `workers.py` | Cancellable background jobs and the prioritised image decoder |
| `app.py` | The main window: menus, panels, dialogs, and job orchestration |
| `widgets.py` | `Section`, the collapsible group the inspector is built from |
| `team.py` | The LAN host, the client outbox, and conflict resolution |

## Decisions worth knowing

### Geometry is normalized

Every coordinate is stored as a fraction of the image, 0–1. That is why annotations survive
re-linking an image, a different preview resolution, and every export: each format denormalizes
on the way out. Pixel values only appear at the edges of the system.

### Undo stores deltas, not snapshots

`Document.change` diffs the incoming annotations against the current ones by id, comparing
object identity first. Editing one shape in a 2000-shape document copies one shape. Each `Edit`
serializes itself once, so writing the recovery draft costs the new edit rather than the whole
history.

### Validation and serialization are memoized per object

Editing builds a *new* `Annotation` for the shape that changed and passes the rest through
untouched, so object identity is a sound cache key. A strong reference is held so an id cannot
be reused, and the vertex count is re-checked to catch in-place edits. This is what makes a
dense image feel instant; see [Performance](../PERFORMANCE.md).

### The database is the project

A project is one `project.sqlite3` in a folder you choose. Schema changes are **appended** to
`MIGRATIONS` in `storage.py` and never edited in place. A project written by a newer Lannotex
refuses to open in an older one rather than risk damage. Every schema change needs a
forward-migration test from a real database of the previous release.

### Caches live outside the project

Thumbnails and tile pyramids are keyed by path, modification time and size, and stored in the
user cache folder, pruned to a budget. Deleting them loses nothing. `LANNOTEX_CACHE_DIR`
redirects them, which is how the tests stay isolated.

### Work happens off the UI thread

Imports, exports, decoding, thumbnails and tile builds all run as cancellable `Job`s on thread
pools. The UI thread only paints and saves. Closing cancels them and waits, rather than asking
you to close again.

## Invariants

Break one of these and something will go quietly wrong:

- **Never mutate an `Annotation` in place** if it may already be in a document or a cache. Build
  a new one. The validation and JSON caches assume this.
- **A slot must not return a value.** PySide6 has over-released the returned object in the past,
  which aborted Python 3.11 at exit.
- **Append migrations, never edit them.** Someone has a database at the old version.
- **Keep `domain`, `storage`, `exporters` and `importers` free of Qt**, so the CLI stays
  display-free.
- **Measure before claiming a speedup.** Every performance claim in the docs has a script under
  `scripts/bench/` and a number with hardware attached.

## Testing

```bash
python -m pytest                     # the whole suite
python -m ruff check src tests       # lint
python scripts/bench/interaction.py --check   # the latency budget CI enforces
```

Property-based tests (hypothesis) check the fast geometry path against the original O(n²)
implementation, which is kept as `polygon_self_intersects_pairwise` precisely so it can be the
oracle. Importers and exporters are tested by round-trip: export a format, read it back, and
compare. CI runs the suite on Windows, macOS and Linux across Python 3.11–3.14.
