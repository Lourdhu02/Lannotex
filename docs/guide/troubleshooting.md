# Troubleshooting

Problems people actually hit, and what to do about them. If yours isn't here, please
[open an issue](https://github.com/Lourdhu02/Lannotex/issues) — include your Lannotex version
(`lannotex --version`), your operating system, and what you were doing.

## Installing

### `OSError: [WinError 206] The filename or extension is too long`

Qt contains deeply nested files and Windows limits paths to 260 characters unless long paths
are enabled. Any one of these fixes it:

- Install with `uv tool install lannotex`, which is not affected.
- Create the virtual environment somewhere short, such as `C:\venvs\lannotex`.
- Enable long paths once, from an administrator PowerShell, then reinstall:

```powershell
New-ItemProperty -Path HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem `
  -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
```

### The window never appears on Linux

Qt needs system libraries that a minimal install may not have:

```bash
sudo apt-get install libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3   # Debian, Ubuntu
sudo dnf install mesa-libEGL libxkbcommon fontconfig dbus-libs                 # Fedora
```

If it still fails, run `lannotex` from a terminal: Qt prints the missing plugin by name.

### Windows or macOS warns that the download is unsafe

The standalone builds are not code-signed yet. On Windows choose **More info → Run anyway**; on
macOS right-click the app and choose **Open**. If you would rather not, install from PyPI
instead — `pip install lannotex` carries no such warning.

## Opening images

### An image shows "Image unavailable"

Lannotex references images where they already live and stores the path **relative to the
project folder**. Moving either one breaks the link. Use **Project → Relink current image…**
and pick the file's new location. Relinking only accepts a file of the same pixel size, so
annotations cannot silently end up on the wrong image.

### A huge image looks soft when I zoom in

The first time you zoom past the preview, Lannotex builds a tile pyramid for that image. Until
it finishes, you are looking at the preview scaled up. The status bar shows the progress; after
it completes, that image opens and zooms instantly forever, because the tiles are cached.

### A 16-bit image looks black, white or flat

16-bit and floating-point images are shown by stretching their actual range to the screen's
0–255. That is a display choice and never changes your file or your exported coordinates. If
the result still looks flat, adjust brightness, contrast and gamma in **Display**.

### Opening a very large image uses a lot of memory the first time

Building the pyramid decodes the image once, which needs memory proportional to its size: about
2.7 GB for a 900 MP image. It happens once per image, and only when you zoom in. Everything
after that is bounded by the size of your window. See [Performance](../PERFORMANCE.md).

## Annotating

### The app will not let me save

Two things block a save, both deliberate:

- **A drawing in progress.** Press ++enter++ to finish the polygon or ++escape++ to discard it.
- **Invalid geometry**, such as a polygon whose edges cross or a box with no area. The message
  says which. Fix or delete that shape.

### My edits seem to have disappeared

They are almost certainly still there. Every edit is written to a recovery draft within 250 ms,
so reopening the project restores both the edits and the undo history. Check that you reopened
the same project folder, and look for **Recovered draft** in the save badge.

### Undo stops working after a while

Undo keeps the last 100 changes for the image you are on. Beyond that, older steps are dropped.

## Exporting

### My export skipped images

`manifest.json` in the export folder lists every skipped image and why. The usual reasons are a
missing source file, geometry that fails validation, or an unsaved recovery draft. Run
**View → Analysis** or `lannotex analyze` first to see them all at once.

### YOLO training says my validation set is empty

Export with the split option (or `--split`). Without it, every image goes in one set and
`train` and `val` point at the same images, which cannot measure anything.

### COCO tools cannot find my images

Use an export from 0.3.0 or later. Before that, `file_name` held the original absolute path.
Exports now include an `images/` folder and reference names inside it.

## Teams

### A reviewer cannot connect

- The host must be running, and bound to `0.0.0.0` rather than `127.0.0.1` to accept other
  machines.
- Give reviewers the host's LAN address, such as `http://192.168.1.20:8765`, never `0.0.0.0`.
- Windows Firewall may need an inbound rule. Lannotex does not change firewall settings.
- Tokens are not stored on disk. After restarting, reconnect from **Team → Reconnect**.

### Two people edited the same image

The second save becomes a conflict instead of overwriting the first. Open **Team**, select the
conflict, and choose **Use team version** or **Publish my version**. Nothing is lost either
way: the host keeps every saved version in its audit history.

## Resetting things

| To reset | Do this |
| --- | --- |
| Panel layout | **View → Panels → Default layout** |
| Image adjustments | **View → Reset image adjustments** |
| Shortcuts and preferences | **Help → Keyboard & preferences** |
| Thumbnail and tile caches | Delete the `Lannotex` folder in your user cache directory; it is rebuilt on demand and holds no project data |
