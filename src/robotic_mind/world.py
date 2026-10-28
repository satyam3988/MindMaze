"""Shared geometry only: object locations are NOT provided to robots or coordinator."""

from robotic_mind.domain.models import Position, Region


def regions() -> list[Region]:
    result = []
    for name, x0, y0 in [("A", -8, 0), ("B", 0, 0), ("C", -8, -8), ("D", 0, -8)]:
        points = []
        for row, y in enumerate([y0 + 1, y0 + 3, y0 + 5, y0 + 7]):
            xs = [x0 + 1, x0 + 3, x0 + 5, x0 + 7]
            for x in xs if row % 2 == 0 else reversed(xs):
                points.append(Position(x=x, y=y, z=3.5))
        result.append(
            Region(
                id=name,
                name=f"Sector {name}",
                xmin=x0,
                xmax=x0 + 8,
                ymin=y0,
                ymax=y0 + 8,
                waypoints=points,
            )
        )
    return result
