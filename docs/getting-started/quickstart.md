# Quick start

This walk-through takes you from a folder of images to an exported dataset in about five
minutes.

## 1. Create a project

Launch `lannotex`. On the Home screen, pick the pipeline that matches your task:

| Pipeline | Use it for | Tools shown |
| --- | --- | --- |
| **Classification** | Tagging whole images (`cat`, `blurry`, `night`) | Class checkboxes only |
| **Object detection** | Locating objects | Bounding boxes |
| **Segmentation** | Tracing exact outlines | Polygons |
| **Combined pipeline** | All of the above | Everything |

Name the project, choose a folder for it, and pick **Solo** (offline, the default) or
**Team**. Lannotex creates one file there: `project.sqlite3`.

You can change the enabled tasks later from **Project → Project tasks…**.

## 2. Import images

Use **+ Folder** or **+ Files** in the Dataset panel, or press ++ctrl+i++. Lannotex scans
folders recursively for JPEG, PNG, and WebP files and checks each one. Damaged files are
reported, not imported.

Images are **referenced, not copied**. The project stores each path relative to the
project folder, so keep the project folder and image folder in the same place relative to
each other, or use **Project → Relink current image…** after moving a file.

## 3. Add labels

Type a label name in **Labels & annotations** and press **+**. Rename or remove labels at
any time. Renaming updates every existing annotation.

## 4. Annotate

- **Classification:** tick the classes that apply. Tick **No target objects in this image**
  for true negatives.
- **Boxes:** press ++b++, select a label, and drag on the image.
- **Polygons:** press ++p++, click to place vertices, and press ++enter++ to finish.

Press ++v++ to select and edit shapes. The full list of controls is in
[Annotating](../guide/annotating.md).

## 5. Save and move on

Press ++ctrl+enter++ to **Save & next**. Your work is also autosaved to a recovery draft
as you go, so closing the app never loses edits.

## 6. Export

Choose **Export** (top right), pick a format and a destination folder. Lannotex writes a
new `Lannotex-export-xxxxxxxx` folder, so it never overwrites a previous export. Images
with problems are skipped and listed. See [Import & export](../guide/import-export.md).

!!! tip "Check before you export"
    **View → Analysis** shows label counts and lists any image with a validation problem,
    a missing source file, or an unsaved draft.
