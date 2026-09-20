"""Evaluate a frozen naive Bayes model on a frozen test split."""

import argparse
import json
from collections import Counter
from pathlib import Path

from .artifacts import (
    artifact_hashes,
    read_json,
    read_jsonl,
    sha256_file,
    utc_now,
    write_json,
    write_jsonl,
)
from .model import MultinomialNaiveBayes, record_text


def _divide(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def evaluate_records(records, model):
    records = list(records)
    if not records:
        raise ValueError("测试集不能为空")
    confusion = Counter()
    mistakes = []
    for record in records:
        actual = record.get("label")
        if actual not in ("ham", "spam"):
            raise ValueError(
                f"{record.get('id', '<unknown>')}: label 必须是 ham 或 spam"
            )
        text = record_text(record)
        scores = model.predict_scores(text)
        predicted = max(model.classes, key=lambda label: (scores[label], label))
        confusion[(actual, predicted)] += 1
        if predicted != actual:
            mistakes.append(
                {
                    "id": record.get("id"),
                    "content_group_id": record.get("content_group_id"),
                    "label": actual,
                    "predicted": predicted,
                    "subject": record.get("subject", ""),
                    "body_preview": record.get("body", "")[:300],
                    "log_scores": scores,
                }
            )
    true_negative = confusion[("ham", "ham")]
    false_positive = confusion[("ham", "spam")]
    false_negative = confusion[("spam", "ham")]
    true_positive = confusion[("spam", "spam")]
    accuracy = _divide(true_positive + true_negative, len(records))
    precision = _divide(true_positive, true_positive + false_positive)
    recall = _divide(true_positive, true_positive + false_negative)
    report = {
        "records": len(records),
        "positive_class": "spam",
        "records_by_label": dict(sorted(Counter(r["label"] for r in records).items())),
        "confusion_matrix": {
            "true_ham_pred_ham": true_negative,
            "true_ham_pred_spam": false_positive,
            "true_spam_pred_ham": false_negative,
            "true_spam_pred_spam": true_positive,
        },
        "metrics": {
            "accuracy": accuracy,
            "precision_spam": precision,
            "recall_spam": recall,
            "f1_spam": _divide(2 * precision * recall, precision + recall),
            "ham_false_positive_rate": _divide(
                false_positive, true_negative + false_positive
            ),
        },
        "misclassified": len(mistakes),
    }
    return report, mistakes


def run_evaluation(test_path, model_path, output):
    test_path = Path(test_path).resolve()
    model_path = Path(model_path).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    records = read_jsonl(test_path)
    model = MultinomialNaiveBayes.from_dict(read_json(model_path))
    report, mistakes = evaluate_records(records, model)

    output.mkdir(parents=True)
    manifest = {
        "state": "in_progress",
        "started_utc": utc_now(),
        "test_path": str(test_path),
        "test_sha256": sha256_file(test_path),
        "model_path": str(model_path),
        "model_sha256": sha256_file(model_path),
    }
    write_json(output / "manifest.json", manifest)
    write_json(output / "evaluation.json", report)
    write_jsonl(output / "misclassified.jsonl", mistakes)
    artifacts = ("evaluation.json", "misclassified.jsonl")
    manifest.update(
        state="complete",
        finished_utc=utc_now(),
        artifact_sha256=artifact_hashes(output, artifacts),
    )
    write_json(output / "manifest.json", manifest)
    return report


def main():
    parser = argparse.ArgumentParser(description="在冻结测试集上评估朴素贝叶斯模型")
    parser.add_argument("test", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/evaluation_v1"))
    args = parser.parse_args()
    try:
        report = run_evaluation(args.test, args.model, args.output)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, f"评估失败：{exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"评估产物：{args.output}")


if __name__ == "__main__":
    main()
