"""Generate the Webots maze; no Webots installation required."""

import argparse
import logging
from pathlib import Path

from vector_maze.webots.world_generator import write_world

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/webots.json")
    parser.add_argument("--output", type=Path, default=ROOT / "webots/worlds/vector_maze.wbt")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.info("Generated %s", write_world(args.config, args.output))


if __name__ == "__main__":
    main()
