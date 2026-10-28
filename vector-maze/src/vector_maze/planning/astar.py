"""Four-connected A* with Manhattan heuristic and unit edge costs."""

from heapq import heappop, heappush
from itertools import count

from vector_maze.interfaces import PathPlanner
from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import Cell


class AStarPlanner(PathPlanner):
    def plan(self, grid: OccupancyGrid, start: Cell, goal: Cell) -> list[Cell]:
        if not grid.is_free(start) or not grid.is_free(goal):
            raise ValueError("Start and goal must be free cells inside the grid")
        sequence = count()
        frontier = [(0, next(sequence), 0, start)]
        costs = {start: 0}
        parents: dict[Cell, Cell] = {}
        while frontier:
            _, _, cost, current = heappop(frontier)
            if cost != costs[current]:
                continue
            if current == goal:
                path = [goal]
                while path[-1] != start:
                    path.append(parents[path[-1]])
                return path[::-1]
            x, y = current
            for neighbor in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
                new_cost = cost + 1
                if grid.is_free(neighbor) and new_cost < costs.get(neighbor, float("inf")):
                    costs[neighbor] = new_cost
                    parents[neighbor] = current
                    heuristic = abs(neighbor[0] - goal[0]) + abs(neighbor[1] - goal[1])
                    heappush(frontier, (new_cost + heuristic, next(sequence), new_cost, neighbor))
        return []
