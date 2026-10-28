"""Generate Warehouse Alpha; ground-truth objects exist only in the world file."""

import json
import math
from pathlib import Path

from robotic_mind.view_geometry import look_at

ROOT = Path(__file__).resolve().parents[1]


def shape(size, color):
    return (
        f"Shape {{ appearance PBRAppearance {{ baseColor {color} roughness 0.6 "
        f"metalness 0.1 }} geometry Box {{ size {size} }} }}"
    )


def box(name, x, y, z, size, color):
    return (
        f'DEF {name} Solid {{ translation {x} {y} {z} name "{name}" '
        f"children [ {shape(size, color)} ] boundingObject Box {{ size {size} }} }}\n"
    )


def generate():
    sensors = json.loads((ROOT / "simulation/webots/config/sensors.json").read_text())
    orientation = " ".join(str(v) for v in look_at([21, -26, 24], [0, 0, 1]))
    world = f"""#VRML_SIM R2025a utf8
WorldInfo {{ basicTimeStep 32 coordinateSystem "ENU" }}
DEF WAREHOUSE_VIEW Viewpoint {{ orientation {orientation} position 21 -26 24 fieldOfView 1.05 }}
Background {{ skyColor [ 0.035 0.045 0.065 ] }}
DirectionalLight {{ direction -0.3 -0.4 -1 intensity 1.3 ambientIntensity 0.6 }}
"""
    world += box("FLOOR", 0, 0, -0.1, "17 17 0.2", "0.12 0.15 0.19")
    for name, x, y, size in [
        ("NORTH", 0, 8.5, "17 0.2 1"),
        ("SOUTH", 0, -8.5, "17 0.2 1"),
        ("EAST", 8.5, 0, "0.2 17 1"),
        ("WEST", -8.5, 0, "0.2 17 1"),
    ]:
        world += box(name, x, y, 0.5, size, "0.3 0.35 0.42")
    for x in range(-8, 9, 2):
        world += box(f"GRID_X_{x + 8}", x, 0, 0.008, "0.015 16 0.01", "0.22 0.27 0.32")
        world += box(f"GRID_Y_{x + 8}", 0, x, 0.008, "16 0.015 0.01", "0.22 0.27 0.32")
    for i, (x, y) in enumerate([(-4, 0), (4, 0), (0, 4), (0, -4)]):
        world += box(f"SHELF_{i}", x, y, 0.5, "1.2 0.7 1", "0.32 0.39 0.46")
    for i, (x, y, color) in enumerate(
        [
            (-5, 5, "0.95 0.025 0.035"),
            (-3, -5, "0.95 0.025 0.035"),
            (5, -3, "0.95 0.025 0.035"),
            (3, 5, "0.03 0.25 0.95"),
            (-5, -3, "1 0.8 0.05"),
            (5, 3, "0.03 0.8 0.5"),
        ]
    ):
        world += box(f"PARCEL_{i}", x, y, 0.2, "0.55 0.55 0.4", color)
    colors = ["0.35 0.9 0.7", "0.45 0.65 1", "0.8 0.65 1", "1 0.75 0.4"]
    for i, (x, y) in enumerate([(-7, 1), (1, 1), (-7, -7), (1, -7)]):
        drone = shape("0.38 0.3 0.15", "0.65 0.7 0.75")
        for a, b in [(-0.28, -0.28), (0.28, -0.28), (-0.28, 0.28), (0.28, 0.28)]:
            drone += (
                f"Transform {{ translation {a} {b} 0 children [ Shape {{ appearance "
                f"PBRAppearance {{ baseColor {colors[i]} metalness 0.3 roughness 0.4 }} "
                "geometry Cylinder { radius 0.17 height 0.025 } } ] }"
            )
        config = sensors.get(f"Scout-0{i + 1}", {})
        yaw = float(config.get("yaw", 0))
        c, s = math.cos(yaw / 2), math.sin(yaw / 2)
        qx, qy, qz, qw = -0.5 * (c + s), 0.5 * (c - s), 0.5 * (c + s), 0.5 * (c - s)
        norm = math.sqrt(qx * qx + qy * qy + qz * qz)
        rotation = f"{qx / norm} {qy / norm} {qz / norm} {2 * math.acos(qw)}"
        drone += (
            f'Camera {{ name "rgb_camera" translation 0 0 -0.12 rotation {rotation} '
            f"width 320 height 240 fieldOfView {config.get('fov', 1.15)} near 0.05 }}"
        )
        world += (
            f"DEF SCOUT_{i + 1} Robot {{ translation {x} {y} 3.5 "
            f'name "Scout-0{i + 1}" supervisor TRUE controller "scout_controller" '
            f"children [ {drone} ] }}\n"
        )
    target = ROOT / "simulation/webots/worlds/warehouse_alpha.wbt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(world, encoding="utf-8")
    return target


if __name__ == "__main__":
    print(generate())
