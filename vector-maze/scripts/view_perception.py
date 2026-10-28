"""Show the six-panel initial snapshot separately from the Webots viewport."""

import argparse
import json
import time
from pathlib import Path

import cv2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "artifacts/perception",
    )
    parser.add_argument("--run-id")
    args = parser.parse_args()
    deadline = time.monotonic() + 180
    while True:
        try:
            metadata = json.loads((args.directory / "metrics.json").read_text())
            if args.run_id is None or metadata.get("run_id") == args.run_id:
                break
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        if time.monotonic() >= deadline:
            raise SystemExit("No initial perception snapshot received within 180 seconds")
        time.sleep(0.25)
    image = cv2.imread(str(args.directory / "debug_view.png"))
    if image is None:
        raise SystemExit("Missing perception debug image")
    title = "Camera map perception - initial snapshot (Esc closes)"
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(title, 704, 840)
    cv2.imshow(title, image)
    while cv2.waitKey(100) != 27 and cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) >= 1:
        pass
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
