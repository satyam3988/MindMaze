"""Installation discovery and validated differential-drive dimensions."""

import os
import shutil
from dataclasses import dataclass, fields
from math import isfinite
from pathlib import Path


@dataclass(frozen=True)
class DriveConfig:
    wheel_radius: float = 0.018
    wheel_separation: float = 0.048
    max_wheel_speed: float = 10.0
    max_linear_velocity: float = 0.08
    max_angular_velocity: float = 1.5

    def __post_init__(self) -> None:
        if any(
            not isfinite(getattr(self, f.name)) or getattr(self, f.name) <= 0 for f in fields(self)
        ):
            raise ValueError("Drive dimensions and speed limits must be finite and positive")


def find_webots(home: str | Path | None = None) -> Path:
    """Use explicit home/WEBOTS_HOME first, then standard install paths and PATH."""
    override = home or os.environ.get("WEBOTS_HOME")
    candidates = (
        [Path(override)]
        if override
        else [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Webots",
            Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
            / "Programs/Webots",
            Path("C:/Program Files (x86)/Webots"),
        ]
    )
    for base in candidates:
        for suffix in ("msys64/mingw64/bin/webots.exe", "webots.exe", "webots"):
            executable = base / suffix
            if executable.is_file():
                return executable.resolve()
    if not override:
        executable = shutil.which("webots")
        if executable:
            return Path(executable).resolve()
    raise FileNotFoundError(
        "Webots executable not found. Install official Webots or set WEBOTS_HOME "
        "to its installation folder (usually C:\\Program Files\\Webots)."
    )
