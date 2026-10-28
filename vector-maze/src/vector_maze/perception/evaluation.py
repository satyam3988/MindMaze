"""Ground truth is used here only for evaluation, never for extraction/planning."""

import logging
from dataclasses import dataclass

from vector_maze.mapping.grid import OccupancyGrid

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MapMetrics:
    total_cells: int
    correctly_classified_cells: int
    incorrect_cells: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    accuracy: float
    occupied_precision: float
    occupied_recall: float
    occupied_iou: float
    occupied_f1: float


def compare_maps(ground_truth: OccupancyGrid, recovered: OccupancyGrid) -> MapMetrics:
    """Compare aligned maps, rejecting shape/resolution mismatches.

    No actual positives gives recall=1. No predicted positives gives precision=1
    only if there are also no actual positives, otherwise 0. Empty union gives
    IoU=1. Thus two all-free maps are a perfect match without division by zero.
    """
    if (ground_truth.width, ground_truth.height, ground_truth.resolution) != (
        recovered.width,
        recovered.height,
        recovered.resolution,
    ):
        raise ValueError("Evaluation requires equal map dimensions and resolution")
    tp = tn = fp = fn = 0
    for actual_row, predicted_row in zip(ground_truth.cells, recovered.cells):
        for actual, predicted in zip(actual_row, predicted_row):
            if actual and predicted:
                tp += 1
            elif not actual and not predicted:
                tn += 1
            elif predicted:
                fp += 1
            else:
                fn += 1
    total = tp + tn + fp + fn
    precision = tp / (tp + fp) if tp + fp else float(tp + fn == 0)
    recall = tp / (tp + fn) if tp + fn else 1.0
    iou = tp / (tp + fp + fn) if tp + fp + fn else 1.0
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.0
    result = MapMetrics(
        total, tp + tn, fp + fn, tp, tn, fp, fn, (tp + tn) / total, precision, recall, iou, f1
    )
    logger.debug("Map evaluation: %s", result)
    return result
