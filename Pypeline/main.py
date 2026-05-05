"""Entrypoint for the overlay pipeline. Loads YAML config, runs the pipeline."""

import argparse
from pathlib import Path

from pypeline.config import PipelineConfig
from pypeline.pipeline import OverlayPipeline


def main() -> None:
    ap = argparse.ArgumentParser(description="Run a Pypeline overlay pipeline.")
    ap.add_argument(
        "--config",
        type=Path,
        default=Path("configs/boat1.yaml"),
        help="Path to the pipeline YAML config (default: configs/boat1.yaml).",
    )
    args = ap.parse_args()

    print(f"running overlay_pipeline with config: {args.config}")
    config = PipelineConfig.from_yaml(args.config)
    OverlayPipeline(config).run()


if __name__ == "__main__":
    main()
