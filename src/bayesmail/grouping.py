"""Content hashing and leakage-prevention grouping."""

from collections import Counter, defaultdict

from .artifacts import canonical_hash


def group_records(records):
    by_full, by_body = defaultdict(list), defaultdict(list)
    for record in records:
        record["normalized_sha256"] = canonical_hash(
            [record["subject"], record["body"]]
        )
        record["body_sha256"] = (
            canonical_hash(record["body"]) if record["body"] else None
        )
        record["content_group_id"] = None
        if record["status"] == "exclude":
            continue
        by_full[record["normalized_sha256"]].append(record)
        if record["body_sha256"]:
            by_body[record["body_sha256"]].append(record)
    for record in records:
        if record["status"] != "exclude":
            key = (
                ["body", record["body_sha256"]]
                if record["body"]
                else ["subject_only", record["normalized_sha256"]]
            )
            record["content_group_id"] = canonical_hash(key)
    groups = []
    for kind, mapping in (("subject_body", by_full), ("body", by_body)):
        for key, members in sorted(mapping.items()):
            if len(members) < 2:
                continue
            conflict = len({record["label"] for record in members}) > 1
            if conflict:
                for record in members:
                    record["status"] = "quarantine"
                    record["quality_flags"] = sorted(
                        set(record["quality_flags"]) | {"cross_label_content_group"}
                    )
            groups.append(
                dict(
                    kind=kind,
                    sha256=key,
                    members=[record["id"] for record in members],
                    labels=dict(Counter(record["label"] for record in members)),
                    cross_label=conflict,
                )
            )
    return groups
