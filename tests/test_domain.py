from labelreview.domain import Annotation, box_valid, polygon_self_intersects, validate
from labelreview.exporters import yolo_line

def test_box_validation_and_yolo():
    ann=Annotation("cat","box",[.1,.2,.5,.6])
    assert box_valid(ann.geometry)
    assert yolo_line(ann, 2) == "2 0.300000 0.400000 0.400000 0.400000"
    assert validate(ann,{"cat"}) == []

def test_bad_geometry_is_rejected():
    assert not box_valid([.3,.1,.2,.9])
    assert polygon_self_intersects([[0,0],[1,1],[0,1],[1,0]])
