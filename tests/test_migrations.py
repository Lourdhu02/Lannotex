"""Forward migration from a v0.2.0 project, and draft durability."""

import json
import os
import subprocess
import sys
import sqlite3
import textwrap

from PIL import Image

from lannotex import storage
from lannotex.domain import Annotation, Document
from lannotex.storage import Project

V0_2_0_MIGRATIONS = 5


def build_v0_2_0_project(root, monkeypatch):
    """A project created by v0.2.0: schema version 5, annotations without label/kind columns."""
    monkeypatch.setattr(storage, "MIGRATIONS", storage.MIGRATIONS[:V0_2_0_MIGRATIONS])
    project = Project(root)
    project.add_label("cat")
    project.add_label("dog")
    path = root / "image.png"
    Image.new("RGB", (64, 48)).save(path)
    image = project.add_image(path, 64, 48)
    # v0.2.0 stored only (id, image_id, data); label and kind lived inside the JSON.
    legacy = [Annotation("cat", "box", [0.1, 0.1, 0.5, 0.5]), Annotation("dog", "polygon", [[0, 0], [1, 0], [1, 1]])]
    with project.conn:
        project.conn.executemany(
            "INSERT INTO annotations VALUES(?,?,?)", [(a.id, image, json.dumps(a.to_dict())) for a in legacy]
        )
        project.conn.execute("UPDATE images SET status='done' WHERE id=?", (image,))
    project.close()
    monkeypatch.undo()
    return image


def columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_v0_2_0_project_upgrades_and_backfills(tmp_path, monkeypatch):
    root = tmp_path / "legacy"
    image = build_v0_2_0_project(root, monkeypatch)

    raw = sqlite3.connect(root / "project.sqlite3")
    assert "label" not in columns(raw, "annotations")
    assert max(r[0] for r in raw.execute("SELECT version FROM migrations")) == V0_2_0_MIGRATIONS
    raw.close()

    project = Project(root, create=False)
    try:
        assert "label" in columns(project.conn, "annotations")
        assert "history" in columns(project.conn, "drafts")
        backfilled = dict(project.conn.execute("SELECT label, kind FROM annotations ORDER BY label"))
        assert backfilled == {"cat": "box", "dog": "polygon"}
        assert [a.label for a in project.load_annotations(image)] == ["cat", "dog"]
    finally:
        project.close()


def test_rename_and_remove_use_the_backfilled_columns(tmp_path, monkeypatch):
    root = tmp_path / "legacy-labels"
    image = build_v0_2_0_project(root, monkeypatch)
    project = Project(root, create=False)
    try:
        project.rename_label("cat", "feline")
        assert sorted(a.label for a in project.load_annotations(image)) == ["dog", "feline"]
        stored = {r[0] for r in project.conn.execute("SELECT label FROM annotations")}
        assert stored == {"feline", "dog"}
        assert (
            json.loads(project.conn.execute("SELECT data FROM annotations WHERE label='feline'").fetchone()[0])["label"]
            == "feline"
        )

        try:
            project.remove_label("feline")
            raise AssertionError("a label still in use must not be removable")
        except ValueError as error:
            assert "in use" in str(error)

        project.add_label("unused")
        project.remove_label("unused")
        assert "unused" not in {r["name"] for r in project.labels()}
    finally:
        project.close()


def test_draft_round_trips_history(tmp_path):
    root = tmp_path / "drafts"
    project = Project(root)
    try:
        project.add_label("cat")
        path = root / "image.png"
        Image.new("RGB", (32, 32)).save(path)
        image = project.add_image(path, 32, 32)

        document = Document([Annotation("cat", "box", [0, 0, 0.4, 0.4])])
        document.change([Annotation("cat", "box", [0.2, 0.2, 0.6, 0.6])])
        project.save_draft(image, document.annotations, False, None, document.history_state())

        annotations, negative, recovered = project.load_state(image)
        assert recovered and not negative and annotations[0].geometry == [0.2, 0.2, 0.6, 0.6]
        restored = Document(annotations, negative)
        restored.restore_history(project.load_history(image))
        assert restored.undo()
        assert restored.annotations[0].geometry == [0, 0, 0.4, 0.4]
    finally:
        project.close()


def test_draft_survives_a_killed_process(tmp_path):
    """synchronous=NORMAL still recovers under WAL when the process dies without closing."""
    root = tmp_path / "crash"
    project = Project(root)
    project.add_label("cat")
    path = root / "image.png"
    Image.new("RGB", (32, 32)).save(path)
    image = project.add_image(path, 32, 32)
    project.close()

    script = textwrap.dedent(f"""
        import os
        from lannotex.storage import Project
        from lannotex.domain import Annotation
        project = Project({str(root)!r}, create=False)
        project.save_draft({image}, [Annotation('cat', 'box', [.3, .3, .8, .8])])
        os._exit(9)
    """)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env)
    assert result.returncode == 9, result.stderr

    reopened = Project(root, create=False)
    try:
        annotations, _, recovered = reopened.load_state(image)
        assert recovered
        assert annotations[0].geometry == [0.3, 0.3, 0.8, 0.8]
    finally:
        reopened.close()


def test_draft_write_does_not_leave_synchronous_relaxed(tmp_path):
    project = Project(tmp_path / "pragma")
    try:
        project.add_label("cat")
        path = tmp_path / "pragma" / "i.png"
        Image.new("RGB", (8, 8)).save(path)
        image = project.add_image(path, 8, 8)
        project.save_draft(image, [Annotation("cat", "box", [0, 0, 0.5, 0.5])])
        assert project.conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
    finally:
        project.close()
