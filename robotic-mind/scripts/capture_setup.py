"""Ask the running Webots supervisor for real renderer captures from four angles."""

import json
import time
from pathlib import Path
from uuid import uuid4


def main():
    root = Path(__file__).resolve().parents[1]
    job = uuid4().hex
    views = [
        {
            "filename": "warehouse-topdown.png",
            "eye": [0, -0.01, 34],
            "target": [0, 0, 0],
            "fov": 1.0,
        },
        {
            "filename": "warehouse-low-angle.png",
            "eye": [14, -19, 10],
            "target": [0, 0, 2],
            "fov": 1.0,
        },
        {"filename": "scout-closeup.png", "focus_self": True, "offset": [2, -2, 1.4], "fov": 0.8},
        {
            "filename": "warehouse-overview.png",
            "eye": [21, -26, 24],
            "target": [0, 0, 1],
            "fov": 1.05,
        },
    ]
    (root / "artifacts/capture-views.json").write_text(
        json.dumps({"job": job, "views": views}), encoding="utf-8"
    )
    result_path = root / "artifacts/capture-result.json"
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result["job"] == job:
                for filename in result["files"]:
                    target = root / "docs/images" / filename
                    assert target.is_file() and target.stat().st_size > 1000
                    print(target.relative_to(root))
                return
        time.sleep(0.2)
    raise RuntimeError("Webots did not capture the views; restart it with the updated controller")


if __name__ == "__main__":
    main()
