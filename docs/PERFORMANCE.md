# Interaction latency on a dense image — 2026-10-24

Reproduce with `python scripts/bench/interaction.py --shapes N`. The script builds one image
holding N shapes (a third boxes, the rest 50–500 vertex polygons), then times the operations a
user triggers by moving the mouse. Hardware: AMD Ryzen 9 8940HX, 23 GiB RAM, Windows 11 build
26300, Python 3.12.8, PySide6 6.11.2. Figures are milliseconds, median of repeated runs.

## Before and after, 200 shapes (~55,000 vertices)

Both columns were measured in the same session on the same machine.

| Operation | Before (p50) | After (p50) | Change |
| --- | ---: | ---: | ---: |
| Validate the document | 4833.5 | 0.115 | 42,000× |
| Move a shape | 108.1 | 0.192 | 563× |
| Drag a vertex | 93.6 | 0.143 | 655× |
| Undo | 30.5 | 0.033 | 923× |
| Save annotations | 4986.0 | 13.8 | 361× |
| Write a recovery draft | 47.1 | 5.4 | 8.7× |
| Load annotations | 50.4 | 16.7 | 3.0× |

Before these changes a 200-shape image froze for about six seconds on every mouse release,
because each release re-ran an O(n²) self-intersection test over every polygon and then
deep-copied the whole document twice to push an undo snapshot.

What changed:

- Self-intersection now sweeps the x axis and compares only edges whose x ranges overlap, so
  the exact same predicate runs on far fewer pairs. The old O(n²) routine is kept as
  `polygon_self_intersects_pairwise` and property tests assert the two always agree.
- Validation results and each annotation's JSON are memoized per annotation object. Editing
  builds a new object for the one shape that changed and passes the rest through untouched, so
  a redraw revalidates and re-serializes one shape rather than all of them.
- Undo stores a delta (added, removed, updated, order) instead of a full document snapshot.
- Recovery drafts are debounced to one write per 250 ms and use `synchronous=NORMAL`; WAL still
  recovers them after a kill, which `test_draft_survives_a_killed_process` asserts.
- `label` and `kind` are indexed columns, so renaming or removing a label is one SQL statement
  instead of parsing every annotation's JSON in Python.
- The canvas caches screen-space polygons per view transform and rejects shapes by bounding box
  before hit-testing or painting them.

## Gated budgets, 600 shapes (~165,000 vertices)

`--check` fails if a p95 exceeds its budget. CI runs `--shapes 400 --check`, a smaller image,
because a shared runner is several times slower than the machine above.

| Operation | p50 | p95 | Budget |
| --- | ---: | ---: | ---: |
| Move a shape | 0.134 | 0.174 | 16 |
| Drag a vertex | 0.118 | 0.186 | 16 |
| Undo | 0.038 | 0.045 | 16 |
| Hit-test a click | 0.198 | 1.518 | 16 |
| Write a recovery draft | 14.4 | 15.7 | 50 |

## Stress run, 2000 shapes (~550,000 vertices)

Far beyond a realistic image; recorded to show where the remaining cost sits.

| Operation | p50 | p95 | Gated |
| --- | ---: | ---: | --- |
| Move a shape | 0.264 | 0.409 | yes |
| Drag a vertex | 0.229 | 0.280 | yes |
| Undo | 0.106 | 0.136 | yes |
| Hit-test a click | 0.628 | 7.549 | yes |
| Write a recovery draft | 50.8 | 54.7 | no |
| Save annotations | 175.7 | 1324.8 | no |
| Load annotations | 301.9 | 350.6 | no |

Editing stays flat because it costs the shapes it touches, not the document size. Saving and
draft writing do not: both serialize every annotation and write it durably, so they scale with
the dataset's bytes — about 5 MB of JSON here, written twice for a save because the audit trail
keeps the saved version. A fixed millisecond budget is the wrong gate for those, so they are
reported instead. Per-row drafts, which would write only the shapes that changed, are the next
step and are not implemented yet.

# Measured desktop baseline — 2026-10-14

Hardware: AMD Ryzen 9 8940HX, approximately 23 GiB usable RAM, Windows 11 build
26300, Python 3.11.9. GPU is not used for these operations. Synthetic files are
generated in a temporary directory by `scripts/benchmark.py` and removed afterward.

| Measurement | Result |
| --- | ---: |
| Main window construction through first processed paint | 86.97 ms |
| Imported JPEG files | 300 |
| Total source bytes | 403,689,900 (~385 MiB) |
| Import time (metadata + verification + SQLite batches) | 1.070 s |
| Import throughput | 280.5 images/s |
| 1920×1080 decode median, 30 samples | 22.24 ms |
| Decode P95 (29th sorted sample) | 25.03 ms |
| Metadata records inserted + paged through | 100,300 |
| Metadata insertion + scrolling | 1.530 s |
| Metadata pages retained | 8 |
| Metadata records retained | 972 (maximum 1,024) |
| Process working set before metadata exercise | 76.13 MiB |
| Process working set after metadata exercise | 81.03 MiB |

Window construction excludes interpreter/Qt imports. Decode timing measures worker
work, not full click-to-display latency or a cold disk. The 300 JPEGs are copies of
one synthetic noisy image, so cache effects matter. The additional 100,000 records
are explicitly metadata-only fixtures; they are not 100,000 real decoded images.
Working set is measured with Windows GetProcessMemoryInfo, not private bytes.

Imports and exports run outside the UI thread. The list is virtualized with an
eight-page metadata cache; decoded preview cache has a 96 MiB budget and serial
decoding. There is no claim of a measured 10 GB real dataset, cold startup, clean-VM
performance, or cross-machine sync latency. Those require representative user data
and the target network. No comparative ranking is claimed.

Reproduce from the repository with `python scripts/benchmark.py` after installing
the package. The script reports hardware/runtime and raw metrics as JSON.
