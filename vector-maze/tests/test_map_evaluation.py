import pytest

from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.perception.evaluation import compare_maps


def test_known_confusion_matrix():
    truth = OccupancyGrid([[1, 1, 0], [0, 1, 0]])
    recovered = OccupancyGrid([[1, 0, 1], [0, 1, 0]])
    metrics = compare_maps(truth, recovered)
    assert metrics.total_cells == 6
    assert metrics.correctly_classified_cells == 4
    assert metrics.incorrect_cells == 2
    assert (
        metrics.true_positive,
        metrics.true_negative,
        metrics.false_positive,
        metrics.false_negative,
    ) == (2, 2, 1, 1)
    assert metrics.accuracy == pytest.approx(4 / 6)
    assert metrics.occupied_precision == pytest.approx(2 / 3)
    assert metrics.occupied_recall == pytest.approx(2 / 3)
    assert metrics.occupied_iou == 0.5


@pytest.mark.parametrize(
    "actual,predicted,expected",
    [
        (0, 0, (1, 1, 1, 1)),
        (1, 1, (1, 1, 1, 1)),
        (1, 0, (0, 0, 0, 0)),
        (0, 1, (0, 0, 1, 0)),
    ],
)
def test_empty_and_extreme_cases(actual, predicted, expected):
    metrics = compare_maps(OccupancyGrid([[actual]]), OccupancyGrid([[predicted]]))
    assert (
        metrics.accuracy,
        metrics.occupied_precision,
        metrics.occupied_recall,
        metrics.occupied_iou,
    ) == expected


@pytest.mark.parametrize("other", [OccupancyGrid([[0, 0]]), OccupancyGrid([[0]], 0.2)])
def test_comparison_rejects_geometry_mismatch(other):
    with pytest.raises(ValueError):
        compare_maps(OccupancyGrid([[0]]), other)
