import unittest
import tempfile
from pathlib import Path

from bayesmail.artifacts import read_json, sha256_file
from bayesmail.preprocessing import build_cleaning_summary, run_cleaning


class CleaningSummaryTests(unittest.TestCase):
    def test_builds_existing_summary_schema_from_records_and_groups(self):
        records = [
            {
                "id": "1",
                "label": "ham",
                "subject": "A",
                "body": "same",
                "status": "keep",
                "actions": ["normalized"],
                "quality_flags": [],
                "before": {
                    "empty_body": False,
                    "replacement_chars": 1,
                    "residual_html": True,
                    "normalized_sha256": "old-1",
                },
                "normalized_sha256": "new-shared",
                "content_group_id": "group-1",
                "text_changed": True,
            },
            {
                "id": "2",
                "label": "spam",
                "subject": "B",
                "body": "same",
                "status": "quarantine",
                "actions": ["normalized"],
                "quality_flags": ["cross_label_content_group"],
                "before": {
                    "empty_body": False,
                    "replacement_chars": 0,
                    "residual_html": False,
                    "normalized_sha256": "old-2",
                },
                "normalized_sha256": "new-shared",
                "content_group_id": "group-1",
                "text_changed": False,
            },
            {
                "id": "3",
                "label": "spam",
                "subject": "",
                "body": "",
                "status": "exclude",
                "actions": [],
                "quality_flags": ["empty_body"],
                "before": {
                    "empty_body": True,
                    "replacement_chars": 0,
                    "residual_html": False,
                    "normalized_sha256": "old-3",
                },
                "normalized_sha256": "new-empty",
                "content_group_id": None,
                "text_changed": False,
            },
        ]
        groups = [
            {
                "kind": "body",
                "members": ["1", "2"],
                "cross_label": True,
            }
        ]

        summary = build_cleaning_summary(records, groups, source_hashes_checked=3)

        self.assertEqual(summary["status_counts"], {"keep": 1, "quarantine": 1, "exclude": 1})
        self.assertEqual(summary["by_label"], {"ham": {"keep": 1}, "spam": {"quarantine": 1, "exclude": 1}})
        self.assertEqual(summary["before"], {"empty_body": 1, "replacement_character": 1, "residual_html_heuristic": 1})
        self.assertEqual(summary["after"]["empty_body"], 1)
        self.assertEqual(summary["duplicates"]["body"], {"groups": 1, "records_in_groups": 2, "excess_records": 1, "cross_label_groups": 1})
        self.assertEqual(summary["duplicates"]["subject_body"]["groups"], 0)
        self.assertEqual(summary["eligible_content_groups"], 1)
        self.assertEqual(summary["original_unique_subject_body"], 3)
        self.assertEqual(summary["cleaned_unique_subject_body"], 1)
        self.assertEqual(summary["changed_records"], 1)
        self.assertEqual(summary["source_hashes_checked"], 3)

    def test_manifest_hashes_domain_implementations(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "corpus"
            (root / "full").mkdir(parents=True)
            (root / "data/000").mkdir(parents=True)
            (root / "full/index").write_text(
                "ham ../data/000/001\n", encoding="utf-8"
            )
            (root / "data/000/001").write_bytes(b"Subject: hello\n\nworld")
            output = base / "output"

            run_cleaning(root, output, {})

            manifest = read_json(output / "manifest.json")
            package = Path(__file__).resolve().parents[1] / "src/bayesmail"
            self.assertEqual(
                manifest["cleaning_policy_sha256"],
                sha256_file(package / "cleaning.py"),
            )
            self.assertEqual(
                manifest["email_parser_sha256"],
                sha256_file(package / "email_parser.py"),
            )


if __name__ == "__main__":
    unittest.main()
