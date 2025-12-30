# tests/test_launch_animation.py
from codogram.launch_animation import FACES, FACE_READY


def test_faces_are_unique():
    """All faces in FACES list are unique."""
    assert len(FACES) == len(set(FACES))


def test_face_ready_not_in_faces():
    """FACE_READY is distinct from animation faces."""
    assert FACE_READY not in FACES
