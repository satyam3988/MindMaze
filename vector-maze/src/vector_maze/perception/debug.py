"""Optional, one-shot visual diagnostics; never used to construct planning maps."""

import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from vector_maze.perception.evaluation import compare_maps


def grid_image(grid, cell_size=40):
    gray = np.where(np.asarray(grid.cells), 35, 240).astype(np.uint8)
    gray = cv2.resize(
        gray, (grid.width * cell_size, grid.height * cell_size), interpolation=cv2.INTER_NEAREST
    )
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)


def debug_images(rgb, result, truth):
    difference = np.zeros((truth.height, truth.width, 3), dtype=np.uint8)
    actual, predicted = np.asarray(truth.cells), np.asarray(result.grid.cells)
    difference[:] = (220, 230, 220)
    difference[(actual == 0) & (predicted == 1)] = (255, 140, 0)
    difference[(actual == 1) & (predicted == 0)] = (255, 0, 100)
    return {
        "camera_rgb": rgb,
        "rectified": result.rectified_rgb,
        "wall_mask": cv2.cvtColor(result.wall_mask, cv2.COLOR_GRAY2RGB),
        "recovered_grid": grid_image(result.grid),
        "ground_truth_grid": grid_image(truth),
        "difference": cv2.resize(
            difference, result.rectified_rgb.shape[1::-1], interpolation=cv2.INTER_NEAREST
        ),
    }


def save_debug_artifacts(directory: Path, rgb, result, truth, run_id):
    directory.mkdir(parents=True, exist_ok=True)
    images = debug_images(rgb, result, truth)
    panels = []
    for name, image in images.items():
        if not cv2.imwrite(str(directory / f"{name}.png"), cv2.cvtColor(image, cv2.COLOR_RGB2BGR)):
            raise OSError(f"Could not save debug artifact {name}")
        panel = np.full((350, 440, 3), 245, dtype=np.uint8)
        scale = min(440 / image.shape[1], 315 / image.shape[0])
        resized = cv2.resize(image, (round(image.shape[1] * scale), round(image.shape[0] * scale)))
        panel[35 : 35 + resized.shape[0], : resized.shape[1]] = resized
        cv2.putText(
            panel,
            name.replace("_", " "),
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )
        panels.append(panel)
    view = np.vstack([np.hstack(panels[i : i + 2]) for i in (0, 2, 4)])
    cv2.imwrite(str(directory / "debug_view.png"), cv2.cvtColor(view, cv2.COLOR_RGB2BGR))
    metrics = asdict(compare_maps(truth, result.grid))
    (directory / "recovered_grid.json").write_text(
        json.dumps(
            {
                "resolution": result.grid.resolution,
                "cells": result.grid.cells,
                "cell_ratios": result.cell_ratios.tolist(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    # Written last: the external viewer uses this run ID as readiness signal.
    (directory / "metrics.json").write_text(
        json.dumps({"run_id": run_id, **metrics}, indent=2) + "\n", encoding="utf-8"
    )
