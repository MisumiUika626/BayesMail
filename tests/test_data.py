import unittest
import tempfile
from pathlib import Path
from email.message import EmailMessage
from bayesmail.data import read_index, read_email, sample_emails

class DataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'full').mkdir()
        (self.root / 'data/000').mkdir(parents=True)
        self.index = self.root / 'full/index'
        self.index.write_text('spam ../data/000/000\nham ../data/000/001\n')
        for name in ('000', '001'):
            (self.root / 'data/000' / name).write_bytes('Subject: 中文主题\n\n中文正文'.encode('gbk'))

    def test_index(self):
        rows = list(read_index(self.root))
        self.assertEqual([(r[0], r[1]) for r in rows], [('000/000', 'spam'), ('000/001', 'ham')])
        self.assertEqual(rows[0][2], self.root / 'data/000/000')

    def test_gbk(self):
        self.assertEqual(read_email(self.root / 'data/000/000', '000/000', 'spam'),
                         dict(id='000/000', label='spam', subject='中文主题', body='中文正文'))

    def test_mime(self):
        msg = EmailMessage()
        msg['Subject'] = '会议通知'
        msg.set_content('请参加会议')
        msg.add_alternative('<p>HTML副本</p>', subtype='html')
        msg.add_attachment('附件机密', filename='secret.txt')
        path = self.root / 'data/000/000'
        path.write_bytes(msg.as_bytes())
        record = read_email(path, '000/000', 'ham')
        self.assertEqual(record['subject'], '会议通知')
        self.assertEqual(record['body'], '请参加会议')

    def test_html(self):
        msg = EmailMessage()
        msg.set_content('<p>优惠 &amp; 活动</p><script>hidden()</script>', subtype='html')
        path = self.root / 'data/000/000'
        path.write_bytes(msg.as_bytes())
        self.assertEqual(read_email(path, '000/000', 'spam')['body'], '优惠 & 活动')

    def test_sample(self):
        self.assertEqual([r['label'] for r in sample_emails(self.root, 1)], ['spam', 'ham'])
        with self.assertRaisesRegex(ValueError, '不足'):
            sample_emails(self.root, 2)
        with self.assertRaises(ValueError):
            sample_emails(self.root, 0)

    def test_invalid_index(self):
        for line in ('unknown ../data/000/000', 'spam ../../outside'):
            with self.subTest(line=line):
                self.index.write_text(line)
                with self.assertRaises(ValueError):
                    list(read_index(self.root))

    def test_missing_file(self):
        (self.root / 'data/000/000').unlink()
        with self.assertRaises(FileNotFoundError):
            sample_emails(self.root, 1)


    def test_cli_output_and_no_overwrite(self):
        import json
        import subprocess
        import sys
        output = self.root / 'samples.jsonl'
        command = [sys.executable, '-m', 'bayesmail.data', str(self.root), '--per-class', '1', '--output', str(output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        records = [json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]['subject'], '中文主题')
        original = output.read_bytes()
        second = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(output.read_bytes(), original)


    def test_stale_base64_header(self):
        path = self.root / 'data/000/000'
        path.write_bytes(b'Content-Type: text/plain; charset=gb2312\nContent-Transfer-Encoding: base64\n\n' + '中文正文'.encode('gbk'))
        self.assertEqual(read_email(path, '000/000', 'ham')['body'], '中文正文')

    def test_stale_multipart_header(self):
        path = self.root / 'data/000/000'
        path.write_bytes(b'Content-Type: multipart/related; boundary=missing\n\n' + '中文正文'.encode('gbk'))
        self.assertEqual(read_email(path, '000/000', 'ham')['body'], '中文正文')
