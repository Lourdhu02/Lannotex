"""The fast sweep must agree with the O(n²) oracle, including on degenerate polygons."""

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from lannotex.domain import (
    Annotation,
    Document,
    polygon_area,
    polygon_self_intersects,
    polygon_self_intersects_pairwise,
    validate,
)

coordinate = st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False, width=32)
vertex = st.lists(coordinate, min_size=2, max_size=2)


def circle(sides, radius=0.4, cx=0.5, cy=0.5):
    return [
        [cx + radius * math.cos(2 * math.pi * i / sides), cy + radius * math.sin(2 * math.pi * i / sides)]
        for i in range(sides)
    ]


@given(st.lists(vertex, min_size=3, max_size=14))
@settings(max_examples=400, deadline=None)
def test_sweep_agrees_with_pairwise_oracle(points):
    assert polygon_self_intersects(points) == polygon_self_intersects_pairwise(points)


@given(st.lists(st.sampled_from([0, 0.25, 0.5, 0.75, 1]), min_size=8, max_size=16))
@settings(max_examples=300, deadline=None)
def test_sweep_agrees_on_grid_aligned_points(values):
    points = [[values[i], values[i + 1]] for i in range(0, len(values) - 1, 2)]
    if len(points) < 3:
        return
    assert polygon_self_intersects(points) == polygon_self_intersects_pairwise(points)


def test_known_shapes():
    assert not polygon_self_intersects([[0, 0], [1, 0], [1, 1], [0, 1]])
    assert polygon_self_intersects([[0, 0], [1, 1], [0, 1], [1, 0]])
    assert not polygon_self_intersects(circle(64))
    assert not polygon_self_intersects(circle(500))
    # A vertex resting exactly on a far edge counts as touching, as it did before the sweep.
    assert polygon_self_intersects([[0, 0], [1, 0], [0.5, 0], [0.5, 1]])


def test_sweep_is_fast_on_a_dense_polygon():
    import time

    points = circle(900)
    start = time.perf_counter()
    assert not polygon_self_intersects(points)
    assert (time.perf_counter() - start) < 0.25


def test_validate_rejects_self_intersection():
    # A pentagram crosses itself and still encloses area, so it reaches the intersection rule.
    star = [
        [0.5 + 0.45 * math.cos(math.radians(90 + 144 * i)), 0.5 + 0.45 * math.sin(math.radians(90 + 144 * i))]
        for i in range(5)
    ]
    assert polygon_self_intersects_pairwise(star)
    assert polygon_area(star) > 1e-10
    assert "Polygon edges intersect" in validate(Annotation("cat", "polygon", star), {"cat"})


def test_history_records_add_remove_update_and_order():
    first = Annotation("cat", "box", [0, 0, 0.4, 0.4])
    second = Annotation("dog", "box", [0.5, 0.5, 0.9, 0.9])
    doc = Document([first, second])

    moved = Annotation("cat", "box", [0.1, 0.1, 0.5, 0.5], first.id)
    assert doc.change([second, moved])
    assert [a.id for a in doc.annotations] == [second.id, first.id]

    assert doc.undo()
    assert [a.id for a in doc.annotations] == [first.id, second.id]
    assert doc.annotations[0].geometry == [0, 0, 0.4, 0.4]

    assert doc.redo()
    assert [a.id for a in doc.annotations] == [second.id, first.id]
    assert doc.annotations[1].geometry == [0.1, 0.1, 0.5, 0.5]

    assert doc.change([second])
    assert doc.undo() and len(doc.annotations) == 2
    assert doc.redo() and [a.id for a in doc.annotations] == [second.id]


def test_history_survives_a_round_trip_through_json():
    doc = Document([Annotation("cat", "box", [0, 0, 0.4, 0.4])])
    doc.change([Annotation("cat", "polygon", [[0, 0], [1, 0], [1, 1]])])
    doc.change([])

    restored = Document(doc.annotations, doc.negative)
    restored.restore_history(doc.history_state())
    assert restored.undo() and len(restored.annotations) == 1
    assert restored.undo() and restored.annotations[0].kind == "box"
    assert not restored.undo()


def test_restore_history_ignores_damaged_state():
    doc = Document([Annotation("cat", "box", [0, 0, 0.4, 0.4])])
    doc.restore_history({"undo": [{"added": [{"nope": 1}]}]})
    assert doc.undo_stack == []
    doc.restore_history(None)
    assert doc.undo_stack == []


def test_editing_does_not_mutate_stored_history():
    original = Annotation("cat", "box", [0, 0, 0.4, 0.4])
    doc = Document([original])
    doc.change([Annotation("cat", "box", [0.2, 0.2, 0.6, 0.6], original.id)])
    doc.annotations[0].geometry[0] = 0.9
    assert doc.undo()
    assert doc.annotations[0].geometry == [0, 0, 0.4, 0.4]
