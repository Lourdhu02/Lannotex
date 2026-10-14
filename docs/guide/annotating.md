# Annotating

## Tools

| Tool | Key | How to use |
| --- | --- | --- |
| Select | ++v++ | Click a shape to select it; drag to move it or its vertices. |
| Box | ++b++ | Drag from one corner to the opposite corner. |
| Polygon | ++p++ | Click to add vertices; ++enter++ finishes, ++escape++ cancels. |

The label selected in the **Labels & annotations** panel is applied to new shapes.

### Editing polygons

- **Move a vertex:** drag it.
- **Insert a vertex:** double-click an edge.
- **Remove a vertex:** select it and press ++shift+delete++.
- **Redraw a shape:** select it and press ++r++. The shape is replaced in place,
  keeping its ID and label.

## Navigating the image

| Action | Control |
| --- | --- |
| Zoom | Mouse wheel (zooms under the pointer), ++ctrl+equal++ / ++ctrl+minus++ |
| Actual pixels (100%) | ++ctrl+1++ |
| Pan | Hold ++space++ and drag, or click and drag in the minimap |
| Fit to window | ++f++ |
| Minimap on/off | ++m++ |
| Pixel grid on/off (from 1200%) | ++g++ |
| Nudge selection | Arrow keys (hold ++shift++ for a 10× step) |
| Focus mode (hide panels) | ++ctrl+shift+f++ |

## Image adjustments

The **Image view** panel has brightness, contrast and gamma sliders for dark, washed-out or
low-contrast images. They change only what you see, never your files or the exported data.
**Reset adjustments**, or **View → Reset image adjustments**, returns to the original.

## Arranging the workspace

The **Dataset**, **Inspector** and **Image view** panels are dockable:

- Drag a panel's title bar to move it to another side, or onto another panel to tab them.
- Use the float button to detach a panel, for example onto a second monitor.
- Close panels you don't need. **View → Panels** lists them all so you can bring them back.
- **View → Panels → Default layout** and **All panels on the right** are one-click presets.
- **Focus mode** (++ctrl+shift+f++) hides every panel. Press it again to restore your layout.

Your layout is saved when you close Lannotex.

## Keyboard reference

| Action | Default |
| --- | --- |
| Command palette: search and run any command | ++ctrl+k++ |
| Save | ++ctrl+s++ |
| Save & next | ++ctrl+enter++ |
| Previous / next image | ++alt+left++ / ++alt+right++ |
| Undo / redo | ++ctrl+z++ / ++ctrl+shift+z++ |
| Duplicate selection | ++ctrl+d++ |
| Delete selection | ++delete++ |
| Open project | ++ctrl+o++ |
| Import images | ++ctrl+i++ |

Every shortcut can be remapped under **Help → Keyboard & preferences**. Shortcuts are
ignored while you type in a text field.

## What Lannotex validates

Saves are rejected, with a message saying why, when an annotation would corrupt a
dataset:

- Boxes must have positive width and height inside the image.
- Polygons need 3–1,000 vertices, a non-zero area, no duplicate vertices, and no
  crossing edges.
- Each class can be applied to an image only once.
- An image marked **No target objects** cannot also contain annotations.

## Coordinates

Geometry is stored **normalized** (0–1) relative to the original image size. Images open
as a fast preview (up to 2,560 px). When you zoom in past that, Lannotex loads the
original pixels in the background, so the image stays sharp up to 6400%. The zoom
readout shows true scale: 100% means one image pixel per screen pixel. Full-resolution
detail is available for images up to 64 megapixels; larger images stay on the preview.
EXIF orientation is respected.

Undo history keeps the last 100 changes for the image you're working on.
