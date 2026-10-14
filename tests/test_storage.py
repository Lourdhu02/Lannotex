from lannotex.domain import Annotation
from lannotex.storage import Project
import pytest

def test_persists_annotations(tmp_path):
    p=Project(tmp_path);p.add_label("cat"); image=p.add_image("images/a.png",100,50)
    saved=Annotation("cat","box",[0,0,.5,.5]);p.save_annotations(image,[saved]);p.close()
    p=Project(tmp_path);loaded=p.load_annotations(image)
    assert loaded[0].id == saved.id and loaded[0].geometry == [0,0,.5,.5]

def test_rename_label_cascades_to_annotations(tmp_path):
    p=Project(tmp_path); p.add_label("cat"); p.add_label("dog")
    image=p.add_image("images/a.png",100,50)
    p.save_annotations(image,[Annotation("cat","box",[0,0,.5,.5])])
    p.rename_label("cat","feline")
    assert [r['name'] for r in p.labels()]==["dog","feline"]
    assert p.load_annotations(image)[0].label=="feline"
    p.close()

def test_draft_is_recovered_then_cleared_on_save(tmp_path):
    p=Project(tmp_path); p.add_label("cat"); image=p.add_image("images/a.png",100,50)
    p.save_draft(image,[Annotation("cat","box",[0,0,.5,.5])])
    anns,negative,recovered=p.load_state(image)
    assert recovered and not negative and len(anns)==1
    p.save_annotations(image,anns)
    _,_,recovered_after=p.load_state(image)
    assert not recovered_after
    p.close()

def test_settings_round_trip(tmp_path):
    p=Project(tmp_path)
    p.set_setting("tasks",["box","polygon"])
    assert p.setting("tasks")==["box","polygon"]
    assert p.setting("missing","fallback")=="fallback"
    p.close()

def test_backup_and_restore(tmp_path):
    source=tmp_path/"src"; dest=tmp_path/"restore"; backup=tmp_path/"backup.sqlite3"
    p=Project(source); p.add_label("cat"); p.close()
    p=Project(source,create=False); p.backup(backup); p.close()
    Project.restore(backup,dest)
    restored=Project(dest,create=False)
    assert [r['name'] for r in restored.labels()]==["cat"]
    restored.close()

def test_newer_project_is_rejected(tmp_path):
    p=Project(tmp_path); p.close()
    p=Project(tmp_path,create=False)
    p.conn.execute("UPDATE migrations SET version=99 WHERE version=2"); p.conn.commit(); p.close()
    with pytest.raises(ValueError):
        Project(tmp_path,create=False)

def test_save_annotations_validates_against_labels(tmp_path):
    p=Project(tmp_path); p.add_label("cat"); image=p.add_image("images/a.png",100,50)
    with pytest.raises(ValueError):
        p.save_annotations(image,[Annotation("dog","box",[0,0,.5,.5])])
    p.close()
