# Phase 5 implementation and validation report

Completed: actual Webots camera-derived map navigation, retaining the original
ground-truth Webots mode and both 2D demos. No physical robot, real camera,
neural model, fiducial localization, ROS, or external inference service was added.

## Files

Created:

- `src/vector_maze/vision/calibration.py` — calibrated homography and coordinate transforms.
- `src/vector_maze/perception/camera_map.py` — RGB conversion, segmentation, extraction, validation.
- `src/vector_maze/perception/debug.py` — optional six-panel artifacts, separate from extraction.
- `scripts/view_perception.py` — independent debug window.
- `tests/test_camera_map.py` — camera, calibration, perception, metrics, navigation, and audit tests.
- `assets/mazes/open.json`, `assets/mazes/serpentine.json` — additional physical maze layouts.
- `configs/webots-open.json`, `configs/webots-serpentine.json` — corresponding mission/calibration settings.
- `docs/camera-navigation-report.md` — this report.

Modified:

- `pyproject.toml` — NumPy/OpenCV dependencies, installed into the existing venv.
- `configs/webots.json` — explicit calibration and configurable perception.
- `src/vector_maze/perception/evaluation.py` — occupied F1 with safe empty cases.
- `src/vector_maze/webots/camera.py` — RGB-only packet transport through the existing CameraSource.
- `src/vector_maze/webots/runtime.py` — camera-map initialization, fail-stop, evaluation, path display.
- `src/vector_maze/webots/world_generator.py` — camera emitter and initially empty route in vision mode.
- `webots/protos/VectorRobot.proto` — overhead RGB receiver device.
- `scripts/launch_webots.py` — explicit map modes and optional debug flags/viewer.
- `tests/test_webots_integration.py` — rendered-camera tests across three mazes and fail-stop test.
- `.vscode/launch.json`, `.vscode/tasks.json` — camera-navigation launch and validation workflows.
- `README.md` — workflows, architecture, calibration, results, limitations, and roadmap.
- `webots/worlds/vector_maze.wbt` — regenerated from the default mission in vision mode.

The shared OccupancyGrid, A*, MazeNavigator, waypoint algorithm, localization
adapter, and motor adapter were reused unchanged. Machine-specific controller
`runtime.ini` files and ignored runtime artifacts were regenerated normally.

## Architecture and calibration

1. The fixed rig's **actual rendered sensor** supplies Webots BGRA bytes.
2. `WebotsCameraSource.capture()` explicitly converts BGRA→packed RGB and returns
   the existing `CameraFrame(width,height,rgb,timestamp)` contract.
3. An emitter/receiver transfers only RGB bytes and frame metadata between the
   camera rig controller and robot controller. Packet validation rejects malformed data.
4. `WebotsReceivedCameraSource.capture()` returns the received RGB CameraFrame.
5. `frame_to_rgb()` returns a **NumPy uint8 RGB ndarray, shape `(480,640,3)`**.
6. `CalibratedOccupancyGridExtractor` receives only RGB and calibration/configuration.
7. Rectification, wall segmentation, morphology, and cell area voting produce the
   existing immutable OccupancyGrid.
8. MazeNavigator derives its footprint-safe grid, invokes the existing A*, and
   passes waypoints to the existing controller and wheel adapter.

The camera is **640×480**, horizontal FOV **1.0 radian**, exactly overhead at
project `(0.65,0.55)` m, Webots `(0.65,-0.55,1.6)` m. Project coordinates are
x-right, y-down, clockwise heading; Webots uses ENU/Z-up with Y sign inverted.
The maze is **13×11 cells**, **0.1 m per cell**, **1.3×1.1 m**. JSON remains
`{"resolution":0.1,"cells":[...]}`, with zero free and one occupied.
Configured start is `(1,1)` (center `(0.15,0.15)` m); goal is `(11,9)`
(center `(1.15,0.95)` m). Neither endpoint is inferred from image colors.

Calibration uses the **wall-top plane at Z=0.12 m**. For camera center `(cx,cy)`,
height `z`, plane `p`, and horizontal FOV `a`:

```text
f = image_width / (2*tan(a/2))
u = image_width/2  + f*(x-cx)/(z-p)
v = image_height/2 + f*(y-cy)/(z-p)
```

The four pixel/world correspondences are:

| Pixel (u,v), approximate | World (x,y), meters |
|---|---|
| (62.742,22.320) | (0,0) |
| (577.258,22.320) | (1.3,0) |
| (577.258,457.680) | (1.3,1.1) |
| (62.742,457.680) | (0,1.1) |

OpenCV computes the image→world homography from these four correspondences.
Pixel→world multiplies homogeneous coordinates and divides by their final component;
world→pixel uses the inverse. World→cell is `(floor(x/0.1),floor(y/0.1))`.
World→canonical scaling is 400 pixels/m, producing **520×440** rectified RGB.
An explicit `image_corners` config can replace the pinhole initializer for measured
or tilted cameras. Tests verify a synthetic perspective image, corners, all cell
centers, invalid polygons, and ROI visibility. Actual Webots runs use the overhead rig.

## Segmentation, exclusion, and safety

OpenCV RGB→HSV uses wall bounds **H=8–32, S=65–255, V=45–255**, with hue in
OpenCV's 0–179 units. Brown cardboard is the wall class. Robot body/white top
belong to an achromatic class, and green/cyan/blue markers belong to separate
foreground color classes, excluded before morphology. This is **Option A:
appearance-based robot segmentation**, using no privileged pose or wall geometry.
The non-wall classes also prevent the green goal, blue start, and perceived path
from becoming obstacles. It assumes the controlled scene's colors, rather than
performing general semantic/instance recognition.

A **3×3 opening**, then **3×3 closing**, cleans the binary mask. Each cell is
occupied if its cleaned wall-pixel count divided by its complete cell area is
**at least 0.75**. This avoids one-pixel sampling. The threshold tolerates wall
side faces intruding into neighboring free cells; walls' rectified top surfaces
occupy almost the entire cell. HSV bounds, kernel, cell threshold, and map-level
plausibility bounds are configurable, using identical settings on all three mazes.

Validation rejects unexpected map dimensions/resolution, outside or occupied
start/goal, or occupancy outside **5–95%**. Current localized pose clearance,
unreachable routes, and swept segment safety are checked by existing navigation.
The planning radius remains **0.043 m (43 mm), no added margin**. Existing
`OccupancyGrid.for_robot(radius)` excludes unsafe cell centers; simulator collision
geometry is untouched. Evaluation keeps the uninflated recovered grid.

The map is extracted once before movement. Missing images time out after five
simulated seconds. Any camera/calibration/extraction/validation/planning failure
stops motors and reports an error. There is no ground-truth recovery path.

## Results

Actual Webots R2025a rigid-body runs, using wheel motors:

| Maze | Correct cells | Accuracy / precision / recall / F1 / IoU | FP / FN | Path waypoints | Simulation seconds | Control steps | Goal error | Wall contact episodes |
|---|---|---|---|---|---|---|---|---|
| simple | 143/143 | all 1.0 | 0 / 0 | 23 | 50.688 | 3,132 | 2.845 mm | 0 |
| open | 143/143 | all 1.0 | 0 / 0 | 19 | 36.080 | 2,219 | 2.835 mm | 0 |
| serpentine | 143/143 | all 1.0 | 0 / 0 | 59 | 126.480 | 7,869 | 2.975 mm | 0 |

All paths include start and goal. All robots physically reached the configured
goal. The simple maze recovered 82 occupied and 61 free cells. Collision counts
are elevated physical contact episodes, using the existing flat-scene classifier.
Ground-truth navigation and the deliberate wall-blocking test also passed.
A wrong HSV wall class failed with `Nonsensical perceived occupancy ratio 0.000`,
zero navigation steps, zero planned waypoints, and zero final linear/angular command.
Both 2D demos independently reached their goal in 1,292 steps with zero collisions;
the synthetic-camera demo retained perfect map recovery.

Quality gates:

- `pytest -q`: **124 passed, 6 skipped** (opt-in real Webots tests).
- `VECTOR_MAZE_WEBOTS_TEST=1` real integration suite: **6 passed**.
- `ruff check .`: **all checks passed**.
- `ruff format --check .`: **56 files already formatted**.

The camera test suite includes BGRA conversion to RGB ndarray, packet transport
and rejection, homography/coordinates, boundary walls, cell area voting, full-map
extraction, morphology, robot/goal exclusion, F1/zero denominators, map validation,
planning/navigation integration, and simulator-independent import checks.

## Data-flow audit

**The planner used the camera-derived map exclusively in vision mode.**

`navigation_main()` obtains its vision branch's `grid` from
`capture_map(WebotsReceivedCameraSource(receiver), calibration, extraction_config,
start, goal)`. `capture_map()` invokes **CameraSource.capture()**, converts RGB,
extracts the occupancy grid, and validates it without accepting any reference map.
`MazeNavigator(grid,...)` receives that recovered grid. A* receives only
`grid.for_robot(radius)`. The JSON reference is loaded **after route planning**,
only into `compare_maps()` and debug rendering. It never changes recovered cells.
World generation is allowed to read JSON to construct physical walls, but in
vision mode it does not invoke A* and starts with an empty path. Runtime then
updates non-collidable path fields with the actual perceived route. The vision
branch does not read wall DEFs or obstacle poses. Ground-truth robot pose remains
the only privileged sensor input used for motion control.

Tests additionally put a wall in an RGB image that is absent from the physical
reference map, record the planner's input, and verify navigation avoids that
image-only wall. The deliberately invalid real-camera configuration stops rather
than continuing with the reference map. These checks complement the source audit.

## Exact VS Code terminal commands

Open `C:\Users\newuser3714\OneDrive\Desktop\hacakathon\vector-maze` in VS Code.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\launch_webots.py --vision-map --run --perception-debug
.\.venv\Scripts\python.exe scripts\launch_webots.py --vision-map --batch --save-debug
.\.venv\Scripts\python.exe scripts\launch_webots.py --vision-map --batch --save-debug --config configs\webots-open.json --artifact-dir artifacts\perception\open
.\.venv\Scripts\python.exe scripts\launch_webots.py --vision-map --batch --save-debug --config configs\webots-serpentine.json --artifact-dir artifacts\perception\serpentine
.\.venv\Scripts\python.exe scripts\launch_webots.py --ground-truth-map --run
.\.venv\Scripts\python.exe scripts\view_perception.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
$env:VECTOR_MAZE_WEBOTS_TEST = '1'
.\.venv\Scripts\python.exe -m pytest tests\test_webots_integration.py -q
Remove-Item Env:\VECTOR_MAZE_WEBOTS_TEST
.\.venv\Scripts\python.exe scripts\run_simulation.py --headless
.\.venv\Scripts\python.exe scripts\run_perception_demo.py --headless
```

F5: **Webots camera map + perception debug**. Task: **Validate Webots camera navigation**.
Logs clearly identify CAMERA PERCEPTION versus GROUND TRUTH JSON, plus pose source.
CLI default retains original ground-truth debug behavior; explicitly use `--vision-map`.
Reload after goal completion. Run one Webots instance of this project at a time
because generated worlds and simulator report paths are shared.

## Debug artifacts

Under `artifacts/perception/`, and separate `simple/`, `open/`, `serpentine/` folders:

- `camera_rgb.png`, `rectified.png`, `wall_mask.png`.
- `recovered_grid.png`, `ground_truth_grid.png`, `difference.png`.
- `debug_view.png` — all six panels.
- `recovered_grid.json` — raw recovered map and per-cell ratios.
- `metrics.json` — counts, accuracy, precision, recall, F1, IoU, current run ID.
- Per-layout `navigation.json` — captured complete physical-run result.
- `fail-stop/navigation.json` — intentionally invalid perception run.

Webots logs, physical-run reports, initial camera image, and perspective start/final
images are under `artifacts/webots/`. Optional snapshots occur once at startup,
with no per-frame image writes. The debug viewer uses run IDs to reject stale
snapshots and runs separately from the simulation viewport and core perception.

## Limitations and next milestone

This phase assumes a static maze, calibrated grid scale/ROI, controlled wall
color and height, and visible wall tops. The homography is plane-specific and
does not remove parallax from objects at other heights. Severe shadows,
appearance changes, blur/noise, occlusion, lens distortion, and dynamic updates
require further validation. The synthetic tilt test validates the architecture;
actual Webots tilt/distortion/randomization work is not claimed. Robot pose still
uses Webots ground truth. No real-camera/robot functionality was added.

OpenCV/NumPy perception is CPU-based; Webots uses normal NVIDIA OpenGL rendering.
The installed renderer on this machine is an **RTX 3060**, despite the original
brief naming an RTX 3070. Global GPU configuration was not modified.

Next milestone: **Phase 6 — Vision-Based Robot Localization**, render/detect a
top-mounted fiducial in the same overhead RGB image and replace
WebotsGroundTruthLocalization with VisionLocalization for x/y/heading. It remains
deliberately unimplemented.

Implementation references: [OpenCV homographies and warping](https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html),
[OpenCV morphology](https://docs.opencv.org/4.x/d9/d61/tutorial_py_morphological_ops.html),
and [Webots emitter transport](https://raw.githubusercontent.com/cyberbotics/webots/R2025a/docs/reference/emitter.md).
