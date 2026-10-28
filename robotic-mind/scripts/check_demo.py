"""Live acceptance test: real Webots cameras, real SDK; configured orchestration provider."""

import argparse
import json
import time
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--expected-objects", type=int, default=3)
    args = parser.parse_args()
    deadline = time.monotonic() + args.timeout
    with httpx.Client(base_url=args.url, timeout=10) as client:
        spaces = client.get("/api/spaces").json()
        space = next(s for s in spaces if s["name"] == "Warehouse Alpha")
        sid = space["id"]
        while time.monotonic() < deadline:
            state = client.get(f"/api/spaces/{sid}").json()
            robots = [
                a
                for a in state["members"]
                if a["member_type"] == "robot" and a["status"] == "online"
            ]
            if len(robots) >= 4:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Four Webots robots did not come online")
        response = client.post(
            f"/api/spaces/{sid}/commands",
            json={
                "text": (
                    "Find all red objects. Split up and avoid searching the same places twice."
                )
            },
        )
        response.raise_for_status()
        mid = response.json()["id"]
        last_stage = ""
        while time.monotonic() < deadline:
            mission = client.get(f"/api/missions/{mid}").json()
            if mission["state"] != last_stage:
                last_stage = mission["state"]
                print("Mission:", last_stage, flush=True)
            if last_stage == "failed":
                raise RuntimeError(mission["error"])
            if last_stage == "complete":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Mission timed out")
        state = client.get(f"/api/spaces/{sid}").json()
        result = mission["result"]
        assert result["unique_objects"] == args.expected_objects, result
        assert result["coverage"] == 1 and result["regions_cleared"] == 4, result
        assert result["participating_agents"] == 4, result
        for robot in robots:
            response = client.get(f"/api/agents/{robot['id']}/camera/latest")
            response.raise_for_status()
            Path(f"artifacts/{robot['id']}.jpg").write_bytes(response.content)
        report = {
            "status": "passed",
            "ai": state["ai"],
            "mission": mission,
            "group_mind": state["group_mind"],
            "members": state["members"],
        }
        Path("artifacts/demo-acceptance.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, indent=2))
        print("PASS: camera-derived discoveries, four agents, all sectors cleared.")
        if state["ai"]["mode"] != "nebius":
            print("Development mock verified; live Nebius acceptance remains unverified.")


if __name__ == "__main__":
    main()
