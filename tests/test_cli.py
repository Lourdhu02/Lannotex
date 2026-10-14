"""Headless CLI: new / analyze / export / --version (no Qt import)."""
import json

import pytest

from lannotex.cli import build_parser, main
from lannotex.storage import Project


def test_parser_exposes_expected_commands():
    parser = build_parser()
    commands = sorted(parser._subparsers._group_actions[0].choices)
    assert commands == ["analyze", "export", "gui", "host", "invite", "new"]


def test_version_flag_exits_zero():
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_new_creates_project(tmp_path):
    folder = tmp_path / "proj"
    main(["new", str(folder)])
    assert (folder / "project.sqlite3").is_file()


def test_analyze_reports_totals(tmp_path, capsys):
    folder = tmp_path / "proj"
    main(["new", str(folder)])
    capsys.readouterr()  # discard the 'new' command output
    project = Project(folder, create=False)
    project.add_label("cat")
    project.add_image("images/a.png", 100, 100)
    project.close()
    main(["analyze", str(folder)])
    report = json.loads(capsys.readouterr().out)
    assert report["total"] == 1
    assert report["unlabeled"] == 1


def test_export_via_cli(tmp_path, capsys):
    root = tmp_path / "proj"; dest = tmp_path / "out"
    Project(root).close()
    main(["export", str(root), str(dest), "--format", "Labelme JSON"])
    assert "Exported 0 images" in capsys.readouterr().out
