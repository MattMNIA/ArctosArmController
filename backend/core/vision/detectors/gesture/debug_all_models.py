from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
DEBUG_SCRIPT = SCRIPT_DIR / "debug_gesture_recognition.py"
DEFAULT_CONFIG = SCRIPT_DIR / "gestures.yml"
DEFAULT_MODELS_DIR = SCRIPT_DIR / "models"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Launch debug_gesture_recognition.py with every gesture model found in the target directory."
        )
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=DEFAULT_MODELS_DIR,
        help="Directory containing .joblib gesture models (defaults to models/ alongside this script).",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        type=Path,
        default=None,
        help="Explicit list of model files to include (overrides auto-discovery).",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.joblib",
        help="Glob used when auto-discovering models (defaults to *.joblib).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Gesture config passed to the debug script (defaults to gestures.yml).",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=None,
        help="Optional camera index override passed through to the debug script.",
    )
    parser.add_argument(
        "--max-hands",
        type=int,
        default=None,
        help="Optional max_hands override.",
    )
    parser.add_argument(
        "--min-detect",
        type=float,
        default=None,
        help="Optional min detection confidence override.",
    )
    parser.add_argument(
        "--min-track",
        type=float,
        default=None,
        help="Optional min tracking confidence override.",
    )
    parser.add_argument(
        "--prob-threshold",
        type=float,
        default=None,
        help="Optional probability threshold override.",
    )
    parser.add_argument(
        "--smoothing-window",
        type=int,
        default=None,
        help="Optional smoothing window override.",
    )
    parser.add_argument(
        "--min-consensus",
        type=int,
        default=None,
        help="Optional min consensus override.",
    )
    parser.add_argument(
        "--max-history",
        type=int,
        default=None,
        help="Optional max history override.",
    )
    parser.add_argument(
        "--save-log",
        type=Path,
        default=None,
        help="If provided, forward --save-log to capture recognizer events.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Echo the command before launching the debug script.",
    )
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def collect_models(args: argparse.Namespace) -> List[Path]:
    if args.models:
        models: Iterable[Path] = args.models
    else:
        models_dir = resolve_path(args.models_dir)
        if not models_dir.exists():
            raise FileNotFoundError(f"Models directory not found: {models_dir}")
        models = sorted(models_dir.glob(args.pattern))
    resolved: List[Path] = []
    for model in models:
        resolved_path = resolve_path(model)
        if not resolved_path.exists():
            raise FileNotFoundError(f"Model file not found: {resolved_path}")
        resolved.append(resolved_path)
    if not resolved:
        raise RuntimeError("No gesture model files were located.")
    return resolved


def build_command(models: List[Path], args: argparse.Namespace) -> List[str]:
    config_path = resolve_path(args.config)
    cmd: List[str] = [
        sys.executable,
        str(DEBUG_SCRIPT),
        "--config",
        str(config_path),
    ]

    if args.camera is not None:
        cmd.extend(["--camera", str(args.camera)])
    if args.max_hands is not None:
        cmd.extend(["--max-hands", str(args.max_hands)])
    if args.min_detect is not None:
        cmd.extend(["--min-detect", str(args.min_detect)])
    if args.min_track is not None:
        cmd.extend(["--min-track", str(args.min_track)])
    if args.save_log is not None:
        cmd.extend(["--save-log", str(resolve_path(args.save_log))])
    if args.prob_threshold is not None:
        cmd.extend(["--prob-threshold", str(args.prob_threshold)])
    if args.smoothing_window is not None:
        cmd.extend(["--smoothing-window", str(args.smoothing_window)])
    if args.min_consensus is not None:
        cmd.extend(["--min-consensus", str(args.min_consensus)])
    if args.max_history is not None:
        cmd.extend(["--max-history", str(args.max_history)])

    for model in models:
        cmd.extend(["--model", str(model)])

    return cmd


def main() -> None:
    args = parse_args()
    models = collect_models(args)
    cmd = build_command(models, args)
    if args.verbose:
        print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()
