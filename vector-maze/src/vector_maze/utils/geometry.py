"""Exact distance from a line segment to an axis-aligned rectangle."""

from math import hypot

from vector_maze.models import Point


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = (
        0.0
        if length2 == 0
        else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    )
    return hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def segment_rectangle_distance(
    a: Point, b: Point, left: float, top: float, right: float, bottom: float
) -> float:
    """Return zero for intersection, otherwise minimum Euclidean separation."""
    lo, hi = 0.0, 1.0
    for start, end, lower, upper in ((a[0], b[0], left, right), (a[1], b[1], top, bottom)):
        delta = end - start
        if delta == 0:
            if not lower <= start <= upper:
                break
        else:
            t1, t2 = sorted(((lower - start) / delta, (upper - start) / delta))
            lo, hi = max(lo, t1), min(hi, t2)
            if lo > hi:
                break
    else:
        return 0.0

    def point_rect(p: Point) -> float:
        return hypot(max(left - p[0], 0, p[0] - right), max(top - p[1], 0, p[1] - bottom))

    corners = ((left, top), (right, top), (right, bottom), (left, bottom))
    return min(point_rect(a), point_rect(b), *(point_segment_distance(p, a, b) for p in corners))
