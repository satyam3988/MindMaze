"""Pygame display of camera frames with planner/debug overlays."""

from collections.abc import Sequence

import pygame

from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import CameraFrame, Cell


class SimulationView:
    def __init__(self, width: int, height: int) -> None:
        pygame.display.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((width, height + 44))
        pygame.display.set_caption("Vector Maze | Space: pause | Esc: exit")
        self.font = pygame.font.Font(None, 24)
        self.clock = pygame.time.Clock()
        self.paused = False

    def process_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_SPACE:
                    self.paused = not self.paused
        return True

    def draw(
        self,
        frame: CameraFrame,
        grid: OccupancyGrid,
        path: Sequence[Cell],
        goal: Cell,
        reached: bool,
    ) -> None:
        surface = pygame.image.frombytes(frame.rgb, (frame.width, frame.height), "RGB")
        scale = frame.width / (grid.width * grid.resolution)

        def pixel(cell: Cell) -> tuple[int, int]:
            x, y = grid.cell_center(cell)
            return round(x * scale), round(y * scale)

        if len(path) > 1:
            pygame.draw.lines(surface, (46, 155, 215), False, [pixel(c) for c in path], 3)
        pygame.draw.circle(surface, (70, 190, 110), pixel(goal), 10, 3)
        self.screen.fill((38, 47, 61))
        self.screen.blit(surface, (0, 0))
        status = "Goal reached" if reached else ("Paused" if self.paused else "Navigating")
        label = self.font.render(f"{status} | Space: pause | Esc: exit", True, (240, 240, 240))
        self.screen.blit(label, (12, frame.height + 12))
        pygame.display.flip()

    def close(self) -> None:
        pygame.quit()
