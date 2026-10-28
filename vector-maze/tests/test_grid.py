import pytest

from vector_maze.mapping.grid import OccupancyGrid


@pytest.mark.parametrize("cells", [[], [[]], [[0], [0, 1]], [[2]]])
def test_rejects_invalid_grid(cells):
    with pytest.raises(ValueError):
        OccupancyGrid(cells)


@pytest.mark.parametrize("resolution", [0, -1, float("nan"), float("inf")])
def test_rejects_invalid_resolution(resolution):
    with pytest.raises(ValueError):
        OccupancyGrid([[0]], resolution)


def test_boundaries_and_world_coordinates():
    grid = OccupancyGrid([[0, 1], [0, 0]], 1.0)
    assert not grid.is_free((-1, 0))
    assert not grid.is_free((0, -1))
    assert not grid.is_free((2, 0))
    assert not grid.is_free((0, 2))
    assert grid.world_to_cell((-0.01, 0.5)) == (-1, 0)
    assert grid.world_to_cell((2.0, 0.5)) == (2, 0)
    assert grid.cell_center((0, 1)) == (0.5, 1.5)
    with pytest.raises(ValueError):
        grid.cell_center((2, 0))


def test_circle_collision_including_corner_and_contact():
    grid = OccupancyGrid([[0, 0, 0], [0, 1, 0], [0, 0, 0]], 1.0)
    assert grid.collides((1.5, 1.5), 0.1)
    assert grid.collides((0.9, 0.9), 0.15)
    assert not grid.collides((0.8, 0.8), 0.25)
    assert grid.collides((0.75, 1.5), 0.25)
    assert grid.collides((0.1, 0.5), 0.1)
    assert grid.collides((3.0, 0.5), 0)


def test_sweep_detects_wall_even_when_both_endpoints_are_free():
    grid = OccupancyGrid([[0, 1, 0], [0, 0, 0]], 1.0)
    assert not grid.collides((0.5, 0.5), 0.1)
    assert not grid.collides((2.5, 0.5), 0.1)
    assert grid.sweep_collides((0.5, 0.5), (2.5, 0.5), 0.1)
    assert not grid.sweep_collides((0.5, 1.5), (2.5, 1.5), 0.1)


def test_grid_copies_input_and_inflates_for_robot():
    cells = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]
    grid = OccupancyGrid(cells, 1.0)
    cells[0][0] = 1
    assert grid.is_free((0, 0))
    safe = grid.for_robot(0.51)
    assert not safe.is_free((0, 1))
    assert grid.is_free((0, 1))
