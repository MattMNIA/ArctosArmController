from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List

SCRIPT_DIR = Path(__file__).resolve().parent
TRAIN_SCRIPT = SCRIPT_DIR / "train_gesture_model.py"
DEFAULT_DATASET = SCRIPT_DIR / "data" / "gesture_dataset.csv"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "models"
DEFAULT_CONFIG = SCRIPT_DIR / "gestures.yml"

MODEL_TYPES: List[str] = [
    "random_forest",
    "extra_trees",
    "sgd",
    "logistic",
    "mlp",
    "naive_bayes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train every supported gesture classifier variant in sequence."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to the gesture dataset CSV (defaults to the repo dataset).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where trained models will be saved (defaults to models/ alongside the script).",
    )
    parser.add_argument(
        "--base-name",
        type=str,
        default=None,
        help="Base filename used for outputs (defaults to the dataset stem).",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        choices=MODEL_TYPES,
        default=MODEL_TYPES,
        help="Subset of model types to train (defaults to all).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Gesture config file passed through to training (defaults to gestures.yml).",
    )
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=None,
        help="Optional override of the test split ratio used during training.",
    )
    parser.add_argument(
        "--trees",
        type=int,
        default=None,
        help="Optional override for tree-based estimators (RandomForest/ExtraTrees).",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Optional override of the estimator max depth.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional override of the random seed.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output files instead of generating unique names.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the full training commands before running them.",
    )
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def build_command(
    model_type: str,
    dataset: Path,
    output_path: Path,
    config: Path,
    args: argparse.Namespace,
) -> List[str]:
    cmd: List[str] = [
        sys.executable,
        str(TRAIN_SCRIPT),
        "--dataset",
        str(dataset),
        "--model-type",
        model_type,
        "--output",
        str(output_path),
        "--config",
        str(config),
    ]

    if args.test_ratio is not None:
        cmd.extend(["--test-ratio", str(args.test_ratio)])
    if args.trees is not None:
        cmd.extend(["--trees", str(args.trees)])
    if args.max_depth is not None:
        cmd.extend(["--max-depth", str(args.max_depth)])
    if args.seed is not None:
        cmd.extend(["--seed", str(args.seed)])
    if args.force:
        cmd.append("--force")

    return cmd


def run_training_sequence(models: Iterable[str], args: argparse.Namespace) -> None:
    dataset = resolve_path(args.dataset)
    output_dir = resolve_path(args.output_dir)
    config_path = resolve_path(args.config)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = args.base_name or dataset.stem

    for model_type in models:
        output_filename = f"{base_name}-{model_type}.joblib"
        output_path = output_dir / output_filename
        cmd = build_command(model_type, dataset, output_path, config_path, args)
        if args.verbose:
            print("Running:", " ".join(cmd))
        print(f"\n=== Training {model_type} => {output_path} ===")
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(f"Command failed for model {model_type} (exit code {result.returncode}). Aborting.")
            raise SystemExit(result.returncode)


def main() -> None:
    args = parse_args()
    run_training_sequence(args.models, args)


if __name__ == "__main__":
    main()
