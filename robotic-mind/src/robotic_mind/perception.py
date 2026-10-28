"""Camera-only color evidence and downward pinhole projection onto object height."""

import math

import cv2
import numpy as np

from robotic_mind_sdk.models import Position


def transform_view(image, brightness=1.0, blur=0, noise=0.0, color_shift=0):
    result = image.astype(np.float32) * brightness
    if noise:
        result += np.random.default_rng().normal(0, noise, result.shape)
    result = np.clip(result, 0, 255).astype(np.uint8)
    if blur:
        result = cv2.GaussianBlur(result, (blur * 2 + 1, blur * 2 + 1), 0)
    if color_shift:
        hsv = cv2.cvtColor(result, cv2.COLOR_BGR2HSV)
        hsv[:, :, 0] = (hsv[:, :, 0].astype(int) + color_shift) % 180
        result = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return result


def detect_red(image, pose: Position, fov=1.15, object_height=0.4, yaw=0.0):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 110, 60]), np.array([10, 255, 255]))
    mask |= cv2.inRange(hsv, np.array([170, 110, 60]), np.array([179, 255, 255]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = image.shape[:2]
    focal = width / (2 * math.tan(fov / 2))
    detections = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 22:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if x < 2 or y < 2 or x + w > width - 2 or y + h > height - 2:
            continue  # Avoid poor coordinates from partially visible objects.
        moments = cv2.moments(contour)
        u, v = moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]
        # Camera looks down -z, image right +x, image down -y at zero yaw.
        dx = (u - width / 2) * (pose.z - object_height) / focal
        dy = -(v - height / 2) * (pose.z - object_height) / focal
        position = Position(
            x=pose.x + dx * math.cos(yaw) - dy * math.sin(yaw),
            y=pose.y + dx * math.sin(yaw) + dy * math.cos(yaw),
            z=object_height,
        )
        confidence = min(0.98, 0.7 + area / 1800)
        detections.append({"position": position, "confidence": confidence, "bbox": (x, y, w, h)})
    return detections
