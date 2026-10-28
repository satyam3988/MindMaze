"""ENU viewer orientation: local +X forward, +Y left, +Z up."""

import math


def look_at(eye, target):
    dx, dy, dz = (b - a for a, b in zip(eye, target, strict=True))
    if not all(math.isfinite(v) for v in (*eye, *target)):
        raise ValueError("View coordinates must be finite")
    if math.sqrt(dx * dx + dy * dy + dz * dz) < 1e-6:
        raise ValueError("View position and target must differ")
    yaw = math.atan2(dy, dx)
    pitch = math.atan2(-dz, math.hypot(dx, dy))
    sy, cy = math.sin(yaw / 2), math.cos(yaw / 2)
    sp, cp = math.sin(pitch / 2), math.cos(pitch / 2)
    x, y, z, w = -sy * sp, cy * sp, sy * cp, cy * cp
    norm = math.sqrt(x * x + y * y + z * z)
    if norm < 1e-9:
        return [0, 0, 1, 0]
    return [x / norm, y / norm, z / norm, 2 * math.atan2(norm, w)]
