import argparse
import os
import subprocess
import sys
from pathlib import Path

from generate_world import generate

ROOT = Path(__file__).resolve().parents[1]


def find_webots():
    candidates = [
        Path(os.environ.get("WEBOTS_HOME", "C:/Program Files/Webots")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Webots",
    ]
    for home in candidates:
        exe = home / "msys64/mingw64/bin/webots.exe"
        if exe.exists():
            return exe
    raise FileNotFoundError("Install Webots R2025a or set WEBOTS_HOME")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--invite", default=os.environ.get("INVITE_CODE"))
    parser.add_argument("--batch", action="store_true")
    args = parser.parse_args()
    if not args.invite:
        parser.error("Supply --invite RM-XXXXXX from seed_demo.py")
    world = generate()
    runtime = ROOT / "simulation/webots/controllers/scout_controller/runtime.ini"
    runtime.write_text(
        f'[python]\nCOMMAND = "{Path(sys.executable).as_posix()}"\n', encoding="utf-8"
    )
    env = os.environ.copy()
    env["INVITE_CODE"] = args.invite
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    command = [str(find_webots()), "--stdout", "--stderr", "--mode=realtime"]
    if args.batch:
        command += ["--batch", "--minimize"]
    command.append(str(world))
    print("Launching", world)
    return subprocess.call(command, cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
