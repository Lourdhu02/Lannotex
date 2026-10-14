# Command line

The `lannotex` command launches the desktop app and runs headless jobs for scripts and CI.
Headless commands don't load Qt, so they work on servers without a display.

```text
lannotex [--version] <command> [options]
```

| Command | Purpose |
| --- | --- |
| *(none)* / `gui` | Launch the desktop app |
| `new` | Create an empty project |
| `analyze` | Validate a project and print a JSON report |
| `export` | Export a project to a folder |
| `invite` | Create a reviewer token for a team project |
| `host` | Serve a team project |

You can also run `python -m lannotex` with the same arguments.

## `lannotex new`

```bash
lannotex new ./my-dataset
```

Creates `my-dataset/project.sqlite3`. The folder is created if needed.

## `lannotex analyze`

```bash
lannotex analyze ./my-dataset
```

Prints a JSON health report to stdout:

```json
{
  "total": 1200,
  "labeled": 1150,
  "unlabeled": 40,
  "negative": 10,
  "boxes": 4310,
  "polygons": 220,
  "classes": 0,
  "distribution": {"car": 3900, "person": 630},
  "problems": ["images/0412.jpg: Missing source image"],
  "drafts": 2
}
```

`problems` lists up to 200 images with validation errors or missing files. Progress goes
to stderr, so stdout stays valid JSON. For example, you can fail a CI job when problems
exist:

```bash
lannotex analyze ./my-dataset | python -c "import json,sys; sys.exit(bool(json.load(sys.stdin)['problems']))"
```

## `lannotex export`

```bash
lannotex export ./my-dataset ./exports --format "YOLO boxes"
```

| Option | Values |
| --- | --- |
| `--format` | `Labelme JSON` (default), `YOLO boxes`, `COCO JSON`, `Classification CSV`, `Native JSONL` |

The command prints the export folder and the number of images included. Skipped images
and their reasons go to stderr. See [Import & export](guide/import-export.md) for the
output layout.

## `lannotex invite`

```bash
lannotex invite ./my-dataset "Alice"
```

Prints a new private reviewer token **once**. The project stores only its hash. Give it
to the reviewer over a private channel.

## `lannotex host`

```bash
lannotex host ./my-dataset --bind 0.0.0.0 --port 8765
lannotex host ./my-dataset --bind 0.0.0.0 --cert server.pem --key server-key.pem
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--bind` | `127.0.0.1` | Interface to listen on. Use `0.0.0.0` for your LAN. |
| `--port` | `8765` | TCP port |
| `--cert`, `--key` | none | PEM files to serve over HTTPS |

Press ++ctrl+c++ to stop. See [Team projects](TEAM.md) for the full workflow and security
notes.
