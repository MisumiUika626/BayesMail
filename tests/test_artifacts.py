import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from bayesmail.artifacts import (
    artifact_hashes,
    canonical_hash,
    read_jsonl,
    sha256_file,
    write_jsonl,
)


class ArtifactTests(unittest.TestCase):
    def test_canonical_hash_uses_stable_compact_unicode_json(self):
        value = {"subject": "会议", "labels": ["ham", "spam"]}
        expected = hashlib.sha256(
            json.dumps(
                value, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

        self.assertEqual(canonical_hash(value), expected)

    def test_jsonl_round_trip_skips_blank_input_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text(
                '{"id": "001", "subject": "会议"}\n\n'
                '{"id": "002", "subject": "offer"}\n',
                encoding="utf-8",
            )

            self.assertEqual(
                read_jsonl(path),
                [
                    {"id": "001", "subject": "会议"},
                    {"id": "002", "subject": "offer"},
                ],
            )

    def test_write_jsonl_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            write_jsonl(path, [{"id": "001"}])

            with self.assertRaises(FileExistsError):
                write_jsonl(path, [{"id": "002"}])

            self.assertEqual(read_jsonl(path), [{"id": "001"}])

    def test_artifact_hashes_match_file_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            first = output / "first.json"
            second = output / "second.jsonl"
            first.write_bytes(b'{"ok": true}\n')
            second.write_bytes(b'{"id": 1}\n')

            self.assertEqual(
                artifact_hashes(output, ["second.jsonl", "first.json"]),
                {
                    "second.jsonl": sha256_file(second),
                    "first.json": sha256_file(first),
                },
            )


if __name__ == "__main__":
    unittest.main()
