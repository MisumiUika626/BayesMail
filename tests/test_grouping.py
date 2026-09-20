import unittest

from bayesmail.cleaning import clean_email, normalize, repair_subject_fold
from bayesmail.grouping import group_records


class GroupingOwnershipTests(unittest.TestCase):
    def test_cleaning_api_is_owned_by_cleaning_module(self):
        record = clean_email(b"Subject: hello\n\nworld", "000/001", "ham")

        self.assertEqual((record["subject"], record["body"]), ("hello", "world"))
        self.assertEqual(normalize("hello\x01world"), "hello world")
        self.assertEqual(repair_subject_fold(b"Subject: plain\n\nbody"), b"Subject: plain\n\nbody")

    def test_grouping_uses_body_and_quarantines_cross_label_content(self):
        records = [
            dict(id="1", label="ham", subject="A", body="same", status="keep", quality_flags=[]),
            dict(id="2", label="spam", subject="B", body="same", status="keep", quality_flags=[]),
        ]

        groups = group_records(records)

        self.assertEqual(records[0]["content_group_id"], records[1]["content_group_id"])
        self.assertEqual([record["status"] for record in records], ["quarantine", "quarantine"])
        self.assertTrue(any(group["cross_label"] for group in groups))

    def test_subject_only_messages_group_by_subject_and_body(self):
        records = [
            dict(id="1", label="ham", subject="A", body="", status="keep", quality_flags=[]),
            dict(id="2", label="ham", subject="B", body="", status="keep", quality_flags=[]),
        ]

        group_records(records)

        self.assertNotEqual(records[0]["content_group_id"], records[1]["content_group_id"])


if __name__ == "__main__":
    unittest.main()
