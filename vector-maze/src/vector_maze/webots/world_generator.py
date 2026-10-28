"""Generate a local-only Webots world from the existing metric occupancy grid."""

import json
import os
from math import acos, sqrt
from pathlib import Path

from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import Cell
from vector_maze.planning.astar import AStarPlanner
from vector_maze.webots.config import DriveConfig
from vector_maze.webots.coordinates import cell_to_webots, project_to_webots


def vector(values: tuple | list) -> str:
    return " ".join(f"{v:.9g}" for v in values)


def viewpoint_rotation(position: tuple, target: tuple) -> tuple[float, float, float, float]:
    """Orient Webots' local +X camera toward a target, keeping +Z upright."""
    forward = [t - p for p, t in zip(position, target)]
    length = sqrt(sum(v * v for v in forward))
    f = [v / length for v in forward]
    length_xy = sqrt(f[0] ** 2 + f[1] ** 2)
    left = [-f[1] / length_xy, f[0] / length_xy, 0]
    up = [-f[2] * left[1], f[2] * left[0], f[0] * left[1] - f[1] * left[0]]
    m = [[f[i], left[i], up[i]] for i in range(3)]
    angle = acos(max(-1, min(1, (m[0][0] + m[1][1] + m[2][2] - 1) / 2)))
    axis = [m[2][1] - m[1][2], m[0][2] - m[2][0], m[1][0] - m[0][1]]
    norm = sqrt(sum(v * v for v in axis))
    return (*(v / norm for v in axis), angle)


def generate_world(
    grid: OccupancyGrid,
    start: Cell,
    goal: Cell,
    settings: dict,
    config_path: Path,
    vision_map: bool = False,
) -> str:
    """Create one solid wall per occupied cell, same scale and full-cell footprint."""
    radius = settings["robot_radius"]
    path = [] if vision_map else AStarPlanner().plan(grid.for_robot(radius), start, goal)
    if not vision_map and not path:
        raise ValueError("Goal unreachable for the Webots robot footprint")
    drive = DriveConfig(**settings["drive"])
    # Model length 60 mm, wheels 8 mm wide; planning circle encloses all geometry.
    footprint = sqrt(0.031**2 + (drive.wheel_separation / 2 + 0.004) ** 2)
    if radius < footprint:
        raise ValueError("Planning radius does not enclose the physical robot")
    width, depth = grid.width * grid.resolution, grid.height * grid.resolution
    center = project_to_webots((width / 2, depth / 2))
    view_position = (center[0], -depth - 0.55, 2.5)
    view_rotation = viewpoint_rotation(view_position, (center[0], center[1], 0.10))
    wall_height = settings["wall_height"]
    controller_dir = (
        Path(__file__).resolve().parents[3] / "webots/controllers/vector_maze_controller"
    )
    config_arg = json.dumps(
        os.path.relpath(config_path.resolve(), controller_dir).replace("\\", "/")
    )
    lines = [
        f"""#VRML_SIM R2025a utf8
# Generated from the same JSON grid used by the 2D simulator. Do not edit walls manually.
EXTERNPROTO "../protos/MazeWall.proto"
EXTERNPROTO "../protos/VectorRobot.proto"
WorldInfo {{
  title "Vector Maze - 3D navigation"
  coordinateSystem "ENU"
  basicTimeStep {settings["basic_time_step"]}
  randomSeed 17
  contactProperties [
    ContactProperties {{ material1 "wheel" material2 "floor" coulombFriction [ 1 ] }}
    ContactProperties {{ material1 "caster" material2 "floor" coulombFriction [ 0.005 ] }}
  ]
}}
Viewpoint {{
  position {vector(view_position)}
  orientation {vector(view_rotation)}
  fieldOfView 1.1
  near 0.01
}}
Background {{ skyColor [ 0.22 0.28 0.36 ] }}
DirectionalLight {{ direction -0.5 -0.5 -1 intensity 1 castShadows TRUE }}
DirectionalLight {{ direction 0.8 0.3 -1 intensity 0.4 castShadows FALSE }}
DEF FLOOR Solid {{
  translation {vector((center[0], center[1], -0.03))}
  name "tabletop"
  contactMaterial "floor"
  children [ Shape {{
    appearance PBRAppearance {{ baseColor 0.84 0.87 0.89 roughness 0.9 metalness 0 }}
    geometry Box {{ size {vector((width + 0.2, depth + 0.2, 0.06))} }}
  }} ]
  boundingObject Box {{ size {vector((width + 0.2, depth + 0.2, 0.06))} }}
}}
"""
    ]
    for y, row in enumerate(grid.cells):
        for x, occupied in enumerate(row):
            if occupied:
                lines.append(f"""DEF WALL_{x}_{y} MazeWall {{
  translation {vector(cell_to_webots(grid, (x, y), wall_height / 2))}
  size {vector((grid.resolution, grid.resolution, wall_height))}
  name "wall_{x}_{y}"
}}""")
    for name, cell, color in (("START", start, "0.1 0.4 1"), ("GOAL", goal, "0.1 0.9 0.25")):
        lines.append(f"""DEF {name} Pose {{
  translation {vector(cell_to_webots(grid, cell, 0.001))}
  children [ Shape {{
    appearance PBRAppearance {{ baseColor {color} roughness 1 metalness 0 }}
    geometry Cylinder {{ radius 0.031 height 0.001 subdivision 32 }}
  }} ]
}}""")
    # Debug route has no boundingObject, therefore cannot collide with the robot.
    points = ", ".join(vector(cell_to_webots(grid, cell, 0.002)) for cell in path)
    indexes = " ".join(str(i) for i in range(len(path))) + " -1"
    lines.append(f"""DEF PLANNED_PATH Shape {{
  appearance Appearance {{ material Material {{ emissiveColor 0.05 0.5 1 }} }}
  geometry DEF PATH_GEOMETRY IndexedLineSet {{
    coord DEF PATH_COORDINATES Coordinate {{ point [ {points} ] }}
    coordIndex [ {indexes} ]
  }}
}}
DEF VECTOR_ROBOT VectorRobot {{
  translation {vector(cell_to_webots(grid, start, 0.001))}
  controllerArgs [ {config_arg} ]
  wheelRadius {drive.wheel_radius}
  wheelSeparation {drive.wheel_separation}
  maxWheelSpeed {drive.max_wheel_speed}
}}
DEF OVERHEAD_CAMERA Robot {{
  translation {vector((center[0], center[1], settings["camera_height"]))}
  name "Overhead camera rig"
  controller "overhead_camera_controller"
  controllerArgs [ {config_arg} ]
  children [
    Emitter {{ name "overhead RGB emitter" channel 11 bufferSize 2000000 }}
    # Non-collidable camera stand, outside the top maze boundary.
    Pose {{
      translation 0 {depth / 2 + 0.12} {-settings["camera_height"] / 2}
      children [ Shape {{
        appearance DEF RIG_MATERIAL PBRAppearance {{
          baseColor 0.13 0.16 0.19 roughness 0.5 metalness 0
        }}
        geometry Box {{ size 0.015 0.015 {settings["camera_height"]} }}
      }} ]
    }}
    Pose {{
      translation 0 {(depth / 2 + 0.12) / 2} 0.05
      children [ Shape {{
        appearance USE RIG_MATERIAL
        geometry Box {{ size 0.015 {depth / 2 + 0.12} 0.015 }}
      }} ]
    }}
    Camera {{
      rotation -0.577350269 0.577350269 0.577350269 2.094395102
      name "overhead camera"
      width {settings["camera_width"]}
      height {settings["camera_height_pixels"]}
      fieldOfView {settings.get("camera_horizontal_fov", 1.0)}
      near 0.01
      far 3
      antiAliasing TRUE
    }}
    Pose {{
      translation 0 0 0.025
      children [ Shape {{
        appearance PBRAppearance {{ baseColor 0.07 0.09 0.11 roughness 0.5 metalness 0 }}
        geometry Box {{ size 0.06 0.045 0.04 }}
      }} ]
    }}
  ]
}}
""")
    return "\n".join(lines) + "\n"


def write_world(config_path: Path, output: Path, vision_map: bool = False) -> Path:
    settings = json.loads(config_path.read_text(encoding="utf-8"))
    grid = OccupancyGrid.load(config_path.parent / settings["maze"])
    text = generate_world(
        grid, tuple(settings["start"]), tuple(settings["goal"]), settings, config_path, vision_map
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    ui_path = output.parent / f".{output.stem}.wbproj"
    if not ui_path.exists():
        ui_path.write_text(
            "Webots Project File version R2025a\n"
            "renderingDevicePerspectives: Overhead camera rig:overhead camera;1;0.4;0;0\n",
            encoding="utf-8",
        )
    return output
