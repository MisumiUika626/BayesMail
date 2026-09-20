import unittest
from email.message import EmailMessage
import tempfile
from pathlib import Path

from bayesmail import preprocessing
from bayesmail.data import read_email
from bayesmail.email_parser import parse_email


class EmailParserTests(unittest.TestCase):
    def test_decodes_gbk_subject_and_body(self):
        parsed = parse_email(
            "Subject: 中文主题\n\n中文正文".encode("gbk"), identifier="000/001"
        )

        self.assertEqual((parsed.subject, parsed.body), ("中文主题", "中文正文"))

    def test_invalid_base64_uses_flat_payload_and_records_metadata(self):
        raw = (
            b"Content-Type: text/plain; charset=gb2312\n"
            b"Content-Transfer-Encoding: base64\n\n"
            + "中文正文".encode("gbk")
        )

        parsed = parse_email(raw, identifier="000/002")

        self.assertEqual(parsed.body, "中文正文")
        self.assertIn("invalid_base64_flat_fallback", parsed.actions)
        self.assertIn("000/002: invalid base64 header; reading flat body", parsed.warnings)

    def test_flat_multipart_fallback_is_visible(self):
        raw = (
            b"Content-Type: multipart/related; boundary=missing\n\n"
            + "中文正文".encode("gbk")
        )

        parsed = parse_email(raw, identifier="000/003")

        self.assertEqual(parsed.body, "中文正文")
        self.assertIn("flat_multipart_fallback", parsed.actions)
        self.assertIn(
            "000/003: multipart header has no boundaries; reading flat body",
            parsed.warnings,
        )

    def test_html_hides_metadata_and_handles_implicit_body_start(self):
        message = EmailMessage()
        message.set_content(
            "<html><head><title>Hidden</title><p>Visible</p>"
            "<script>hidden()</script></html>",
            subtype="html",
        )

        parsed = parse_email(message.as_bytes(), identifier="000/004")

        self.assertEqual(" ".join(parsed.body.split()), "Visible")
        self.assertIn("html_visible_text", parsed.actions)

    def test_prefers_plain_text_and_excludes_attachments(self):
        message = EmailMessage()
        message["Subject"] = "会议"
        message.set_content("正文")
        message.add_alternative("<p>HTML 副本</p>", subtype="html")
        message.add_attachment("附件机密", filename="secret.txt")

        parsed = parse_email(message.as_bytes(), identifier="000/005")

        self.assertEqual((parsed.subject, parsed.body.strip()), ("会议", "正文"))
        self.assertNotIn("附件机密", parsed.body)

    def test_empty_plain_falls_back_to_html(self):
        message = EmailMessage()
        message.set_content(" ")
        message.add_alternative("<p>有效正文</p>", subtype="html")

        parsed = parse_email(message.as_bytes(), identifier="000/006")

        self.assertEqual(" ".join(parsed.body.split()), "有效正文")
        self.assertIn("empty_plain_html_fallback", parsed.actions)

    def test_sampling_and_cleaning_share_decoded_content(self):
        message = EmailMessage()
        message["Subject"] = "活动通知"
        message.set_content(
            "<html><head><title>隐藏</title></head><body><p>优惠</p><p>服务</p></body></html>",
            subtype="html",
        )
        raw = message.as_bytes()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mail"
            path.write_bytes(raw)
            sampled = read_email(path, "000/007", "spam")
        cleaned = preprocessing.clean_email(raw, "000/007", "spam")

        self.assertEqual(
            (sampled["subject"], sampled["body"]),
            (cleaned["subject"], cleaned["body"]),
        )

    def test_cleaning_audit_keeps_fallback_warning(self):
        raw = (
            b"Content-Type: text/plain; charset=gb2312\n"
            b"Content-Transfer-Encoding: base64\n\n"
            + "中文正文".encode("gbk")
        )

        cleaned = preprocessing.clean_email(raw, "000/008", "ham")

        self.assertIn(
            "000/008: invalid base64 header; reading flat body",
            cleaned["parser_warnings"],
        )

    def test_metadata_text_after_meta_stays_hidden_until_body_content(self):
        raw = (
            b"Content-Type: text/html; charset=utf-8\n\n"
            b"<html><head><meta name=x>secret metadata"
            b"<p>Visible body</p></html>"
        )

        parsed = parse_email(raw, identifier="000/009")

        self.assertEqual(" ".join(parsed.body.split()), "Visible body")


if __name__ == "__main__":
    unittest.main()
