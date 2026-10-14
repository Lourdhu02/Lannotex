# Coming from LabelMe

Lannotex reads and writes LabelMe's JSON format, so you can bring an existing dataset over
and still hand files back to LabelMe users.

## Import a LabelMe folder

1. Create a project (**Combined pipeline** enables every tool).
2. Choose **Project → Import LabelMe folder…** and select the folder that contains your
   LabelMe `.json` files. Subfolders are included. Use **Import annotations…** for a single
   file.
3. Lannotex reads each file, finds the image through its `imagePath`, checks that the
   dimensions match, and creates any missing labels.

Your LabelMe JSON files and images are left untouched.

### What carries over

| LabelMe | Lannotex |
| --- | --- |
| `rectangle` shapes | Bounding boxes |
| `polygon` shapes | Polygons |
| `circle` shapes | Polygons (32 points around the circle) |
| `rotation` (rotated rectangle) shapes | Polygons with the four corners |
| `flags` set to `true` | Image classes |
| Image files via `imagePath` | Referenced in place, not copied |

!!! warning "Current limitations"
    - `point`, `line`, `linestrip` and `mask` shapes are **skipped**. The rest of each file
      still imports, and the import summary lists how many of each were skipped. Support
      for these shapes is planned.
    - Shapes with invalid geometry, such as a polygon with fewer than 3 points, are skipped
      and listed the same way.
    - `imageData` embedded in the JSON isn't used. The image file must exist on disk.
    - `group_id`, `description`, and per-shape `flags` aren't imported.

## Export back to LabelMe

**Export → Labelme JSON** writes one LabelMe-compatible file per image. LabelMe can open
these. Lannotex adds a `lannotex` block and a `lannotex_id` per shape, which LabelMe
ignores and which let Lannotex re-import without creating duplicates.

## How they compare

Both are good tools with different strengths. This comparison reflects LabelMe's
published features and pricing as of October 2026.

| | Lannotex | LabelMe |
| --- | --- | --- |
| License | MIT | GPL-3.0 (source), EULA (paid desktop app) |
| Standalone desktop app | Free | Paid one-time license |
| YOLO export | Free | Pro tier |
| COCO export | Yes | Yes |
| Project storage | One SQLite database per dataset | One JSON file per image |
| Autosave & crash recovery | Always on: recovery drafts + transactional saves | Optional autosave |
| Validation before saving | Geometry (bounds, self-intersection, zero area) and labels | Label names |
| Team review with conflict handling | Built in (LAN host) | No |
| Headless export / validation | `lannotex export`, `lannotex analyze` | Conversion scripts in its examples |
| AI-assisted annotation (SAM, YOLO-World) | Not yet | Yes |
| Circles, lines, points, rotated boxes, masks | Not yet | Yes |
| Video annotation | No | Yes |
| UI languages | English | 20 |

If you depend on AI-assisted segmentation or the extra shape types today, LabelMe is
the better fit for now. If you want a free, permissively licensed tool that keeps large
datasets organized and safe, Lannotex is built for that.
