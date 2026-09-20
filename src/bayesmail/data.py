"""Read TREC06C indexes and MIME emails using only the standard library."""

import argparse
import json
import warnings
from collections import Counter
from pathlib import Path

from .email_parser import decode_bytes as _decode
from .email_parser import parse_email

def read_index(root):
    """Yield (id, label, absolute_path); root contains full/index and data/."""
    root = Path(root).resolve()
    data_dir = (root / "data").resolve()
    index = root / "full/index"
    seen = set()
    with index.open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            fields = line.split()
            if len(fields) != 2 or fields[0] not in ("ham", "spam"):
                raise ValueError(f"{index}:{number}: 需要 ham/spam 和邮件路径")
            label, relative = fields
            path = (index.parent / relative).resolve()
            if not path.is_relative_to(data_dir) or path == data_dir:
                raise ValueError(f"{index}:{number}: 邮件路径必须位于 data/ 内")
            identifier = path.relative_to(data_dir).as_posix()
            if identifier in seen:
                raise ValueError(f"{index}:{number}: 重复邮件 {identifier}")
            seen.add(identifier)
            yield identifier, label, path


def read_email(path, identifier, label):
    """Decode subject and body; prefer plain text and exclude attachments."""
    if label not in ("ham", "spam"):
        raise ValueError("label 必须是 ham 或 spam")
    parsed = parse_email(Path(path).read_bytes(), identifier=identifier)
    for message in parsed.warnings:
        warnings.warn(message)
    return dict(
        id=identifier,
        label=label,
        subject=" ".join(parsed.subject.split()),
        body=" ".join(parsed.body.split()),
    )


def sample_emails(root, per_class=10):
    """Return the first N distinct messages of each class in index order.

    This is an inspection sample, not a training/test split.
    """
    if per_class < 1:
        raise ValueError("per_class 必须大于 0")
    counts = Counter()
    records = []
    for identifier, label, path in read_index(root):
        if counts[label] >= per_class:
            continue
        records.append(read_email(path, identifier, label))
        counts[label] += 1
        if counts["ham"] == counts["spam"] == per_class:
            return records
    raise ValueError(f"样本不足：需要每类 {per_class} 封，实际 {dict(counts)}")


def main():
    parser = argparse.ArgumentParser(
        description="读取 TREC06C，按索引顺序抽取每类邮件供检查"
    )
    parser.add_argument("root", type=Path, help="包含 full/index 和 data/ 的目录")
    parser.add_argument("--per-class", type=int, default=10)
    parser.add_argument(
        "--output", type=Path, default=Path("reports/email_samples.jsonl")
    )
    args = parser.parse_args()
    try:
        records = sample_emails(args.root, args.per_class)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"读取失败：{exc}\n")
    print(f"已输出 {len(records)} 封邮件：{dict(Counter(r['label'] for r in records))}")
    print(f"文件：{args.output}")


if __name__ == "__main__":
    main()
