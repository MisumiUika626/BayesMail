"""CLI orchestration for versioned, auditable email cleaning."""

import argparse
import json
import warnings
from collections import Counter
from pathlib import Path

from .artifacts import (
    artifact_hashes,
    canonical_hash,
    read_jsonl,
    utc_now,
    write_json,
    write_jsonl,
)
from .cleaning import (
    HTML_TAG,
    RULE_VERSION,
    clean_email,
    digest,
    normalize,
    repair_raw,
    repair_subject_fold,
)
from .data import read_email, read_index
from .grouping import group_records


def build_cleaning_summary(records, groups, source_hashes_checked):
    actions = Counter(action for record in records for action in record["actions"])
    flags = Counter(flag for record in records for flag in record["quality_flags"])
    before = dict(
        empty_body=sum(record["before"]["empty_body"] for record in records),
        replacement_character=sum(
            record["before"]["replacement_chars"] > 0 for record in records
        ),
        residual_html_heuristic=sum(
            record["before"]["residual_html"] for record in records
        ),
    )
    after = dict(
        empty_body=sum(not record["body"] for record in records),
        replacement_character=sum(
            "\ufffd" in record["subject"] + record["body"] for record in records
        ),
        residual_html_heuristic=sum(
            bool(HTML_TAG.search(record["body"])) for record in records
        ),
    )
    stats = {}
    for kind in ("subject_body", "body"):
        matching = [group for group in groups if group["kind"] == kind]
        stats[kind] = dict(
            groups=len(matching),
            records_in_groups=sum(len(group["members"]) for group in matching),
            excess_records=sum(len(group["members"]) - 1 for group in matching),
            cross_label_groups=sum(group["cross_label"] for group in matching),
        )
    return dict(
        rules_version=RULE_VERSION,
        total=len(records),
        status_counts=dict(Counter(record["status"] for record in records)),
        by_label={
            label: dict(
                Counter(
                    record["status"]
                    for record in records
                    if record["label"] == label
                )
            )
            for label in ("ham", "spam")
        },
        actions=dict(actions),
        quality_flags=dict(flags),
        before=before,
        after=after,
        duplicates=stats,
        eligible_content_groups=len(
            {
                record["content_group_id"]
                for record in records
                if record["status"] == "keep"
            }
        ),
        original_unique_subject_body=len(
            {record["before"]["normalized_sha256"] for record in records}
        ),
        cleaned_unique_subject_body=len(
            {
                record["normalized_sha256"]
                for record in records
                if record["status"] != "exclude"
            }
        ),
        changed_records=sum(record["text_changed"] for record in records),
        source_hashes_checked=source_hashes_checked,
    )


def run_cleaning(root, output, overrides, source_audit=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output == root or output.is_relative_to(root):
        raise ValueError("Output must be outside the source corpus")
    if output.exists():
        raise FileExistsError(output)
    index = list(read_index(root))
    if not index:
        raise ValueError("Empty index")
    missing = set(overrides) - {row[0] for row in index}
    if missing:
        raise ValueError(f"Reviewed IDs not in index: {sorted(missing)}")
    previous = {}
    if source_audit:
        previous = {row["id"]: row for row in read_jsonl(source_audit)}
        if set(previous) != {row[0] for row in index}:
            raise ValueError("Source audit does not cover this index")
    output.mkdir(parents=True)
    manifest = dict(
        state="in_progress",
        rules_version=RULE_VERSION,
        started_utc=utc_now(),
        root=str(root),
        index_sha256=digest((root / "full/index").read_bytes()),
        cleaner_sha256=digest(Path(__file__).read_bytes()),
        parser_sha256=digest(Path(__file__).with_name("data.py").read_bytes()),
        cleaning_policy_sha256=digest(
            Path(__file__).with_name("cleaning.py").read_bytes()
        ),
        email_parser_sha256=digest(
            Path(__file__).with_name("email_parser.py").read_bytes()
        ),
        overrides_sha256=canonical_hash(overrides),
        source_audit=str(source_audit) if source_audit else None,
    )
    write_json(output / "manifest.json", manifest)
    write_json(output / "reviewed_overrides.json", overrides)
    records = []
    for number, (identifier, label, path) in enumerate(index, 1):
        raw = path.read_bytes()
        if previous and (
            digest(raw) != previous[identifier]["raw_sha256"]
            or label != previous[identifier]["label"]
        ):
            raise ValueError(f"{identifier}: source audit mismatch")
        row = clean_email(raw, identifier, label, overrides)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            old = read_email(path, identifier, label)
        row["before"] = dict(
            subject_chars=len(old["subject"]),
            body_chars=len(old["body"]),
            replacement_chars=(old["subject"] + old["body"]).count("\ufffd"),
            normalized_sha256=canonical_hash(
                [" ".join(old["subject"].split()), " ".join(old["body"].split())]
            ),
            empty_body=not old["body"],
            residual_html=bool(HTML_TAG.search(old["body"])),
        )
        row["text_changed"] = [old["subject"], old["body"]] != [
            row["subject"],
            row["body"],
        ]
        records.append(row)
        if number % 10000 == 0:
            print(f"Cleaned {number}/{len(index)}", flush=True)
    groups = group_records(records)
    write_jsonl(output / "records.jsonl", records)
    write_jsonl(
        output / "cleaned.jsonl",
        (record for record in records if record["status"] == "keep"),
    )
    write_jsonl(
        output / "quarantine.jsonl",
        (record for record in records if record["status"] == "quarantine"),
    )
    write_jsonl(
        output / "excluded.jsonl",
        (record for record in records if record["status"] == "exclude"),
    )
    write_jsonl(output / "duplicate_groups.jsonl", groups)
    result = build_cleaning_summary(records, groups, len(previous))
    write_json(output / "summary.json", result)
    manifest.update(
        state="complete",
        finished_utc=utc_now(),
        artifact_sha256=artifact_hashes(
            output,
            [
                path.name
                for path in sorted(output.iterdir())
                if path.name != "manifest.json"
            ],
        ),
    )
    write_json(output / "manifest.json", manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="清洗邮件并重新查重，不划分或训练"
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--overrides", type=Path)
    parser.add_argument("--source-audit", type=Path)
    args = parser.parse_args()
    overrides = (
        json.loads(args.overrides.read_text(encoding="utf-8-sig"))
        if args.overrides
        else {}
    )
    try:
        run_cleaning(args.root, args.output, overrides, args.source_audit)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"清洗失败（未完成的目录不可用于下游）：{exc}\n")


if __name__ == "__main__":
    main()
