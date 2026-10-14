from lannotex.domain import Annotation, Document, box_valid, polygon_self_intersects, validate, validate_all
from lannotex.exporters import yolo_line

def test_box_validation_and_yolo():
    ann=Annotation("cat","box",[.1,.2,.5,.6])
    assert box_valid(ann.geometry)
    assert yolo_line(ann, 2) == "2 0.300000 0.400000 0.400000 0.400000"
    assert validate(ann,{"cat"}) == []

def test_bad_geometry_is_rejected():
    assert not box_valid([.3,.1,.2,.9])
    assert polygon_self_intersects([[0,0],[1,1],[0,1],[1,0]])

def test_document_undo_redo():
    doc = Document([Annotation("cat", "box", [0, 0, .5, .5])])
    assert doc.change([Annotation("cat", "box", [.1, .1, .6, .6])])
    assert doc.undo()
    assert doc.annotations[0].geometry == [0, 0, .5, .5]
    assert doc.redo()
    assert doc.annotations[0].geometry == [.1, .1, .6, .6]

def test_noop_change_does_not_push_history():
    doc = Document([Annotation("cat", "box", [0, 0, .5, .5])])
    assert not doc.change(doc.annotations)
    assert doc.undo_stack == []

def test_validate_all_rejects_duplicate_ids():
    first = Annotation("cat", "box", [0, 0, .5, .5])
    second = Annotation("cat", "box", [.1, .1, .6, .6])
    second.id = first.id
    errors = validate_all([first, second], {"cat"})
    assert any("Duplicate annotation ID" in e for e in errors)

def test_validate_all_rejects_duplicate_class():
    anns = [Annotation("cat", "classification"), Annotation("cat", "classification")]
    assert any("Duplicate class" in e for e in validate_all(anns, {"cat"}))

def test_classification_cannot_carry_geometry():
    assert validate(Annotation("cat", "classification", [0, 0, .5, .5]), {"cat"})

def test_negative_image_cannot_have_annotations():
    anns = [Annotation("cat", "classification")]
    assert validate_all(anns, {"cat"}, negative=True)
