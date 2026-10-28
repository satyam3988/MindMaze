"""Actual rendered Webots camera frames using the shared RGB contract."""

import struct
from collections.abc import Callable
from typing import Protocol

from vector_maze.interfaces import CameraSource
from vector_maze.models import CameraFrame


class CameraDevice(Protocol):
    def getWidth(self) -> int: ...
    def getHeight(self) -> int: ...
    def getImage(self) -> bytes: ...


class WebotsCameraSource(CameraSource):
    """Convert Webots R2025a BGRA to packed RGB without altering geometry."""

    def __init__(self, device: CameraDevice, clock: Callable[[], float]) -> None:
        self.device = device
        self.clock = clock

    def capture(self) -> CameraFrame:
        width, height = self.device.getWidth(), self.device.getHeight()
        bgra = self.device.getImage()
        if not bgra or len(bgra) != width * height * 4:
            raise RuntimeError("Camera has no valid frame yet; enable it and step Webots first")
        rgb = bytearray(width * height * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
        return CameraFrame(width, height, bytes(rgb), self.clock())


_HEADER = struct.Struct("<4sIId")


def encode_frame(frame: CameraFrame) -> bytes:
    return _HEADER.pack(b"RGB1", frame.width, frame.height, frame.timestamp) + frame.rgb


class WebotsReceivedCameraSource(CameraSource):
    """Transport the rig's actual RGB frame, never simulator wall information."""

    def __init__(self, receiver):
        self.receiver = receiver

    def capture(self) -> CameraFrame:
        if self.receiver.getQueueLength() == 0:
            raise RuntimeError("No overhead camera packet available")
        data = bytes(self.receiver.getBytes())
        self.receiver.nextPacket()
        if len(data) < _HEADER.size:
            raise ValueError("Truncated overhead RGB packet")
        magic, width, height, timestamp = _HEADER.unpack_from(data)
        if magic != b"RGB1" or len(data) != _HEADER.size + width * height * 3:
            raise ValueError("Invalid overhead RGB packet")
        return CameraFrame(width, height, data[_HEADER.size :], timestamp)
