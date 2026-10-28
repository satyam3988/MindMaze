import math

import cv2
import numpy as np
import pytest

from robotic_mind.view_geometry import look_at


@pytest.mark.parametrize(
    "eye,target",
    [
        ([18, -22, 20], [0, 0, 1.2]),
        ([0, -0.01, 25], [0, 0, 0]),
        ([2, -2, 4.9], [0, 0, 3.5]),
        ([0, 0, 0], [1, 0, 0]),
    ],
)
def test_view_orientation_points_at_target(eye, target):
    axis = look_at(eye, target)
    rotation, _ = cv2.Rodrigues(np.array(axis[:3], dtype=float) * axis[3])
    direction = np.array(target, float) - np.array(eye, float)
    direction /= np.linalg.norm(direction)
    assert np.allclose(rotation @ np.array([1, 0, 0]), direction)
    assert math.isclose(np.linalg.det(rotation), 1)


def test_invalid_view_coordinates():
    with pytest.raises(ValueError):
        look_at([0, 0, 0], [0, 0, 0])
    with pytest.raises(ValueError):
        look_at([float("nan"), 0, 0], [0, 0, 0])
