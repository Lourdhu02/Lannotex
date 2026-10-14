from labelreview.domain import Annotation
from labelreview.storage import Project

def test_persists_annotations(tmp_path):
    p=Project(tmp_path);p.add_label("cat"); image=p.add_image("images/a.png",100,50)
    saved=Annotation("cat","box",[0,0,.5,.5]);p.save_annotations(image,[saved]);p.close()
    p=Project(tmp_path);loaded=p.load_annotations(image)
    assert loaded[0].id == saved.id and loaded[0].geometry == [0,0,.5,.5]
