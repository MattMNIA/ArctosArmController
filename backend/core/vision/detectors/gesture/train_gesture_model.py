from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np

try:  # pandas is required for training but may not be installed yet
    import pandas as pd  # type: ignore[import]
except ImportError as exc:  # pragma: no cover - runtime check
    raise ImportError("pandas is required to train the gesture model. Install it via requirements.txt.") from exc

from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import GaussianNB
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import LabelEncoder

PROJECT_ROOT = Path(__file__).resolve().parents[0]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gesture_recognizer import load_gesture_config  # noqa: E402


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
        default=PROJECT_ROOT / "gestures.yml",
        help="Gesture config file to embed into model metadata",
    )
    parser.add_argument(
        "--model-type",
        choices=[
            "random_forest",
            "extra_trees",
            "sgd",
            "logistic",
            "mlp",
            "naive_bayes",
        ],
        default="random_forest",
        help="Classifier to train. Defaults to random_forest for parity with the existing model.",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="Optional label appended to the output filename when avoiding overwrites.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists instead of creating a unique name.",
    )
    return parser.parse_args()


def ensure_unique_output_path(
    base_path: Path,
    model_type: str,
    tag: Optional[str],
    force: bool,
) -> Path:
    base_path = base_path.resolve()
    if force or not base_path.exists():
        return base_path

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    suffix_parts = [model_type, timestamp]
    if tag:
        suffix_parts.insert(1, tag)

    candidate = base_path.with_name(
        f"{base_path.stem}_{'_'.join(suffix_parts)}{base_path.suffix}"
    )
    counter = 1
    while candidate.exists():
        candidate = base_path.with_name(
            f"{base_path.stem}_{'_'.join(suffix_parts)}_{counter}{base_path.suffix}"
        )
        counter += 1
    return candidate


def build_classifier(args: argparse.Namespace) -> Tuple[Any, Dict[str, Any]]:
    """Create the classifier specified by CLI arguments and accompanying metadata."""

    model_type = args.model_type
    if model_type == "random_forest":
        classifier = RandomForestClassifier(
            n_estimators=args.trees,
            max_depth=args.max_depth,
            random_state=args.seed,
            class_weight="balanced_subsample",
            n_jobs=-1,
        )
    elif model_type == "extra_trees":
        classifier = ExtraTreesClassifier(
            n_estimators=args.trees,
            max_depth=args.max_depth,
            random_state=args.seed,
            class_weight="balanced_subsample",
            n_jobs=-1,
        )
    elif model_type == "sgd":
        classifier = SGDClassifier(
            loss="log_loss",
            penalty="l2",
            learning_rate="optimal",
            alpha=1e-4,
            max_iter=2000,
            tol=1e-3,
            random_state=args.seed,
            class_weight="balanced",
        )
    elif model_type == "logistic":
        classifier = LogisticRegression(
            solver="lbfgs",
            max_iter=1000,
            class_weight="balanced",
            random_state=args.seed,
            multi_class="auto",
        )
    elif model_type == "mlp":
        classifier = MLPClassifier(
            hidden_layer_sizes=(64, 32),
            activation="relu",
            max_iter=750,
            random_state=args.seed,
        )
    elif model_type == "naive_bayes":
        classifier = GaussianNB()
    else:  # pragma: no cover - defensive fallback
        raise ValueError(f"Unknown model type: {model_type}")

    metadata = {
        "model_type": model_type,
        "classifier_params": classifier.get_params(),
    }
    return classifier, metadata


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

    classifier, classifier_meta = build_classifier(args)
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
    payload["metadata"].update(classifier_meta)
    return payload


def main() -> None:
    args = parse_args()
    df = load_dataset(args.dataset)
    payload = train_model(df, args)

    output_base = args.output
    if not output_base.is_absolute():
        output_base = (PROJECT_ROOT / output_base).resolve()
    output_path = ensure_unique_output_path(output_base, args.model_type, args.tag, args.force)
    if output_path != output_base:
        print(f"Output file {output_base} exists; saving to {output_path} instead.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_entry = payload.setdefault("metadata", {})
    if isinstance(metadata_entry, dict):
        metadata_entry["output_path"] = str(output_path)
    else:
        payload["metadata"] = {"output_path": str(output_path)}
    joblib.dump(payload, output_path)
    print(f"Model saved to {output_path}")

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
