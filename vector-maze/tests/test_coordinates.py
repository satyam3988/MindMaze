import pytest

from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.vision.coordinates import PixelGridTransform


def test_pixel_grid_world_round_trips_match_existing_grid():
    transform = PixelGridTransform(48, 0.1)
    grid = OccupancyGrid([[0] * 13] * 11, 0.1)
    assert transform.grid_dimensions(624, 528) == (13, 11)
    assert transform.pixels_per_meter == 480
    for y in range(grid.height):
        for x in range(grid.width):
            cell = (x, y)
            world = transform.cell_center_world(cell)
            pixel = transform.cell_center_pixel(cell)
            assert world == grid.cell_center(cell)
            assert transform.world_to_pixel(world) == pytest.approx(pixel)
            assert transform.pixel_to_world(pixel) == pytest.approx(world)
            assert transform.pixel_to_cell(pixel) == cell
            assert transform.world_to_cell(world) == grid.world_to_cell(world) == cell
    assert transform.cell_center_pixel((2, 1)) == (120, 72)
    assert transform.cell_pixel_bounds((2, 1)) == (96, 48, 144, 96)


def test_half_open_edges_negative_coordinates_and_no_clipping():
    transform = PixelGridTransform(20, 1)
    assert transform.pixel_to_cell((0, 0)) == (0, 0)
    assert transform.pixel_to_cell((19.999, 20)) == (0, 1)
    assert transform.pixel_to_cell((20, 0)) == (1, 0)
    assert transform.pixel_to_cell((-0.001, -20)) == (-1, -1)
    assert transform.world_to_cell((-0.01, 1)) == (-1, 1)
    assert transform.pixel_to_world((60, 40)) == (3, 2)


@pytest.mark.parametrize(
    "pixels,resolution", [(0, 1), (-1, 1), (1.5, 1), (1, 0), (1, float("inf"))]
)
def test_invalid_calibration(pixels, resolution):
    with pytest.raises(ValueError):
        PixelGridTransform(pixels, resolution)


@pytest.mark.parametrize("width,height", [(0, 2), (2, -1), (3, 4), (4, 3)])
def test_invalid_image_dimensions(width, height):
    with pytest.raises(ValueError):
        PixelGridTransform(2, 1).grid_dimensions(width, height)
