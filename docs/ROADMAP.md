# Roadmap

What Lannotex is aiming at, what is done, and what is deliberately out of scope. Dates are not
promised; order is.

**The goal:** the fastest, most reliable native labelling tool, that runs AI locally and opens
images of any size. No account, no subscription, MIT.

## Done

| | |
| --- | --- |
| **Instant editing** | Validation, undo and saving no longer scale with document size. A dense image went from a six-second freeze per edit to 0.2 ms. CI enforces a 16 ms budget. |
| **Any image size** | Disk-cached tile pyramids. A 900 MP TIFF reopens in 0.1 s and pans using under 200 MB. |
| **Formats** | Export to Labelme, YOLO boxes and segments, Pascal VOC, COCO, CSV and native JSONL, with a reproducible train/val/test split. Import LabelMe, COCO, YOLO and VOC. |
| **Crash safety** | Recovery drafts, transactional saves, and undo history that survives a kill. |
| **Teams** | Optional LAN host, per-reviewer tokens, background sync, explicit conflict resolution, audit history. |
| **Reach** | PyPI, standalone builds for Windows, macOS and Linux, and a headless CLI for CI. |

## Next

### Streaming decode

Opening a 900 MP image for the *first* time still costs about 2.8 s and several GB, because
Pillow cannot decode part of a TIFF. Reading native tiles in a compiled core fixes cold opens
and peak memory, and brings in the runtime the AI work needs. Measured alternatives and why
they were rejected are in [Performance](PERFORMANCE.md).

### More shapes

Rotated boxes, points, polylines, keypoints with skeletons, and brush masks. Per-object
attributes — a schema per label, enforced at save. These are what most LabelMe and CVAT users
ask for first.

### AI assist, on your machine

Click-to-polygon with SAM, and pre-labelling with your own YOLO `.onnx`, as proposals you
accept or reject. Shipped as an optional extra so the base install stays small. Models are
downloaded only when you ask, verified by checksum, and run locally. No third-party service,
ever.

### Dataset health

Label distribution, tiny and huge outliers, duplicate and near-duplicate images, overlapping
shapes, and missing required attributes — in the Analysis panel and as
`lannotex validate --strict` for CI.

### Shipping like software

An MSIX package and a Microsoft Store listing, winget, a Flathub manifest, and a notarized
macOS build. Signed, so no warnings.

## Later

Video: frames, tracks and interpolation. Active learning, to put the most useful unlabelled
image in front of you next. Review roles, inter-annotator agreement and a visual version diff
for teams.

## Not planned

A hosted cloud service, accounts or billing. Text, audio, 3D or DICOM annotation. Enterprise
SSO. These are good products; they are not this one.

## Principles

- Local projects and exports stay fully usable with no account, licence key or network.
- Source images are never altered, and geometry stays normalized so it survives everything.
- No telemetry, and no network traffic you did not ask for.
- Every performance claim ships with a script and a number.
