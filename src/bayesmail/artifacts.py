"""Shared helpers for deterministic, auditable pipeline artifacts."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value):
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(encoded)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_jsonl(path, rows):
    with Path(path).open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def artifact_hashes(output, names):
    output = Path(output)
    return {name: sha256_file(output / name) for name in names}
