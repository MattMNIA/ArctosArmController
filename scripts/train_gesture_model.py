from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np

try:  # pandas is required for training but may not be installed yet
    import pandas as pd  # type: ignore[import]
except ImportError as exc:  # pragma: no cover - runtime check
    raise ImportError("pandas is required to train the gesture model. Install it via requirements.txt.") from exc

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.vision.gesture_recognizer import load_gesture_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a gesture classification model from collected samples."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "data" / "gesture_dataset.csv",
        help="CSV dataset produced by collect_gesture_dataset.py",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "models" / "gesture_classifier.joblib",
        help="Path to save the trained model",
    )
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=0.2,
        help="Fraction of the dataset reserved for evaluation",
    )
    parser.add_argument(
        "--trees",
        type=int,
        default=250,
        help="Number of trees in the random forest classifier",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Optional maximum depth for each tree",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "backend" / "config" / "gestures.yml",
        help="Gesture config file to embed into model metadata",
    )
    return parser.parse_args()


def load_dataset(dataset_path: Path) -> pd.DataFrame:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found at {dataset_path}")
    df = pd.read_csv(dataset_path)
    required_columns = {"gesture", "handedness"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Dataset missing required columns: {sorted(missing)}")
    feature_columns = sorted(
        (col for col in df.columns if col.startswith("f")),
        key=lambda name: int(name[1:]) if name[1:].isdigit() else name,
    )
    if not feature_columns:
        raise ValueError("Dataset does not contain any feature columns (expected columns prefixed with 'f').")
    df = df.dropna(subset=feature_columns + ["gesture"])
    return df


def train_model(df: pd.DataFrame, args: argparse.Namespace) -> Dict[str, object]:
    feature_columns = sorted(
        (col for col in df.columns if col.startswith("f")),
        key=lambda name: int(name[1:]) if name[1:].isdigit() else name,
    )
    X = df[feature_columns].to_numpy(dtype=np.float32)
    encoder = LabelEncoder()
    y = encoder.fit_transform(df["gesture"].tolist())

    test_ratio = args.test_ratio if 0.0 < args.test_ratio < 0.5 else 0.2
    if len(df) < 10:
        X_train, X_test, y_train, y_test = X, X, y, y
    else:
        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=test_ratio,
            stratify=y if len(np.unique(y)) > 1 else None,
            random_state=args.seed,
        )

    classifier = RandomForestClassifier(
        n_estimators=args.trees,
        max_depth=args.max_depth,
        random_state=args.seed,
        class_weight="balanced_subsample",
        n_jobs=-1,
    )
    classifier.fit(X_train, y_train)

    if len(X_test) > 0:
        y_pred = classifier.predict(X_test)
        unique_classes = np.unique(y_test)
        target_labels = encoder.inverse_transform(unique_classes)
        report = classification_report(
            y_test,
            y_pred,
            labels=unique_classes,
            target_names=target_labels,
            output_dict=True,
            zero_division=0,
        )
    else:
        report = {"overall": {"precision": 1.0, "recall": 1.0, "f1-score": 1.0}}

    payload = {
        "classifier": classifier,
        "label_encoder": encoder,
        "feature_names": feature_columns,
        "metadata": {
            "trained_at": datetime.utcnow().isoformat() + "Z",
            "dataset_path": str(args.dataset),
            "test_ratio": test_ratio,
            "samples": len(df),
            "gestures": sorted(df["gesture"].unique()),
            "report": report,
        },
    }
    return payload


def main() -> None:
    args = parse_args()
    df = load_dataset(args.dataset)
    payload = train_model(df, args)

    model_dir = args.output.parent
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(payload, args.output)
    print(f"Model saved to {args.output}")

    gesture_config = load_gesture_config(args.config)
    print("Configured gestures:")
    for item in gesture_config.get("gestures", []):
        label = item.get("label")
        event = item.get("event")
        print(f"  - {label} -> {event}")

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        report = metadata.get("report", {})
        if isinstance(report, dict):
            overall = report.get("accuracy") or report.get("overall", {})
            if isinstance(overall, dict):
                precision = overall.get("precision", "n/a")
                recall = overall.get("recall", "n/a")
                f1 = overall.get("f1-score", "n/a")
                print(f"Evaluation -> precision: {precision}, recall: {recall}, f1: {f1}")


if __name__ == "__main__":
    main()
