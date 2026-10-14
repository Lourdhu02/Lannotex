# Projects & safety

## What's in a project

A project is a folder that contains one file:

```text
my-dataset/
├── project.sqlite3        # labels, annotations, drafts, settings, history
├── project.sqlite3-wal    # SQLite journal (present while open)
└── project.sqlite3-shm
```

Source images stay wherever they already are. The database stores each image's path
**relative to the project folder**. If the images live on a different drive on Windows,
the path is stored absolute.

Projects created by an older Lannotex are upgraded automatically when opened. A project
saved by a *newer* version refuses to open in an older one rather than risk damage.

## How your work is protected

| Layer | What it does |
| --- | --- |
| **Recovery drafts** | Every edit is written to a per-image draft immediately. |
| **Autosave** | Drafts are committed 700 ms after you stop editing. |
| **Transactional saves** | A save either completes fully or changes nothing. |
| **Validation** | Invalid geometry is rejected before it is stored. |
| **Durable writes** | SQLite runs in WAL mode with full sync; exports are written atomically. |

## Backup and restore

**Project → Backup project…** writes a consistent copy of the database. It's safe to
run while the project is open.

**Project → Restore backup…** checks the backup's integrity, then restores it into an
**empty** folder. It never overwrites an existing project.

!!! warning "Backups don't include images"
    A backup holds annotations, drafts, settings, and team history, not the image files.
    Back up your source images separately.

## Moved an image?

Choose **Project → Relink current image…** and pick the file's new location. Lannotex
only accepts a file with the same dimensions, so existing annotations can't end up
misaligned.

## Version control

Commit **exports** (Labelme JSON, COCO, YOLO, or native JSONL) to Git, not the live
`project.sqlite3`. The binary database doesn't diff or merge.
