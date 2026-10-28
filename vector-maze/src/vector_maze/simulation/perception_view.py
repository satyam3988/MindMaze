"""Debug-only map comparison display; perception does not depend on this view."""

from collections.abc import Sequence

import pygame

from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import CameraFrame, Cell, Pose2D
from vector_maze.perception.evaluation import MapMetrics
from vector_maze.simulation.view import SimulationView
from vector_maze.vision.coordinates import PixelGridTransform


class PerceptionView(SimulationView):
    """RGB, ground truth, recovered navigation map, and error map in four panels."""

    def __init__(self, frame: CameraFrame, transform: PixelGridTransform) -> None:
        self.transform = transform
        self.panel_width = min(frame.width, 390)
        self.panel_height = max(1, round(frame.height * self.panel_width / frame.width))
        self.row_height = self.panel_height + 32
        super().__init__(2 * self.panel_width, 2 * self.row_height + 52)
        pygame.display.set_caption("Vector Maze Perception | Space: pause | Esc: exit")

    def draw_comparison(
        self,
        frame: CameraFrame,
        ground_truth: OccupancyGrid,
        recovered: OccupancyGrid,
        metrics: MapMetrics,
        path: Sequence[Cell],
        goal: Cell,
        pose: Pose2D,
        radius: float,
        steps: int,
        collisions: int,
        reached: bool,
    ) -> None:
        """Ground truth is strictly an evaluation overlay, never a planning input."""
        rgb = pygame.image.frombytes(frame.rgb, (frame.width, frame.height), "RGB")

        def map_surface(grid: OccupancyGrid, differences: bool = False) -> pygame.Surface:
            surface = pygame.Surface((frame.width, frame.height))
            for y, row in enumerate(grid.cells):
                for x, occupied in enumerate(row):
                    if differences:
                        actual = ground_truth.cells[y][x]
                        color = (
                            ((220, 70, 70) if occupied else (230, 165, 45))
                            if occupied != actual
                            else (225, 235, 225)
                        )
                    else:
                        color = (38, 47, 61) if occupied else (242, 245, 249)
                    left, top, right, bottom = self.transform.cell_pixel_bounds((x, y))
                    pygame.draw.rect(surface, color, (left, top, right - left, bottom - top))
            return surface

        known = map_surface(ground_truth)
        extracted = map_surface(recovered)
        difference = map_surface(recovered, differences=True)

        def pixel(cell: Cell) -> tuple[int, int]:
            return tuple(round(v) for v in self.transform.cell_center_pixel(cell))

        if len(path) > 1:
            pygame.draw.lines(extracted, (46, 155, 215), False, [pixel(c) for c in path], 3)
        pygame.draw.circle(extracted, (70, 190, 110), pixel(goal), 10, 3)
        center = tuple(round(v) for v in self.transform.world_to_pixel((pose.x, pose.y)))
        pygame.draw.circle(
            extracted,
            (238, 157, 45),
            center,
            max(1, round(radius * self.transform.pixels_per_meter)),
        )
        self.screen.fill((38, 47, 61))
        panels = (
            ("Synthetic RGB (live)", rgb),
            ("Ground truth (evaluation only)", known),
            ("Recovered map + navigation", extracted),
            ("Errors: red=FP, orange=FN", difference),
        )
        for i, (title, surface) in enumerate(panels):
            x, y = (i % 2) * self.panel_width, (i // 2) * self.row_height
            self.screen.blit(self.font.render(title, True, (240, 240, 240)), (x + 8, y + 7))
            self.screen.blit(
                pygame.transform.scale(surface, (self.panel_width, self.panel_height)), (x, y + 32)
            )
        status = "Goal reached" if reached else ("Paused" if self.paused else "Navigating")
        lines = (
            f"Accuracy {metrics.accuracy:.1%} | IoU {metrics.occupied_iou:.3f} | "
            f"Errors {metrics.incorrect_cells}/{metrics.total_cells}",
            f"{status} | Steps {steps} | Collisions {collisions}",
            "Static map from initial RGB frame | Space: pause | Esc: exit",
        )
        for i, line in enumerate(lines):
            self.screen.blit(
                self.font.render(line, True, (240, 240, 240)), (8, 2 * self.row_height + 8 + i * 26)
            )
        pygame.display.flip()
