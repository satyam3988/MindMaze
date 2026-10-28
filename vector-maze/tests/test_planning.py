from collections import deque
from random import Random

import pytest

from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.planning.astar import AStarPlanner


def test_astar_finds_optimal_path_around_wall():
    grid = OccupancyGrid([[0, 1, 0], [0, 1, 0], [0, 0, 0]])
    path = AStarPlanner().plan(grid, (0, 0), (2, 0))
    assert path[0] == (0, 0) and path[-1] == (2, 0)
    assert len(path) == 7
    assert all(grid.is_free(cell) for cell in path)
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(path, path[1:]))


def test_unreachable_goal():
    assert AStarPlanner().plan(OccupancyGrid([[0, 1, 0]]), (0, 0), (2, 0)) == []


def test_start_equals_goal():
    assert AStarPlanner().plan(OccupancyGrid([[0]]), (0, 0), (0, 0)) == [(0, 0)]


@pytest.mark.parametrize("start,goal", [((-1, 0), (0, 0)), ((0, 0), (2, 0)), ((0, 0), (1, 0))])
def test_invalid_endpoints(start, goal):
    with pytest.raises(ValueError):
        AStarPlanner().plan(OccupancyGrid([[0, 1]]), start, goal)


def test_astar_agrees_with_breadth_first_search_on_seeded_maps():
    random = Random(17)
    for _ in range(40):
        cells = [[int(random.random() < 0.3) for _ in range(8)] for _ in range(8)]
        cells[0][0] = cells[7][7] = 0
        grid = OccupancyGrid(cells)
        queue = deque([((0, 0), 0)])
        seen = {(0, 0)}
        expected = None
        while queue:
            (x, y), distance = queue.popleft()
            if (x, y) == (7, 7):
                expected = distance
                break
            for cell in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if grid.is_free(cell) and cell not in seen:
                    seen.add(cell)
                    queue.append((cell, distance + 1))
        path = AStarPlanner().plan(grid, (0, 0), (7, 7))
        assert (len(path) - 1 if path else None) == expected
