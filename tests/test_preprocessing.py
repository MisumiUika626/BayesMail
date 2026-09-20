import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from email.message import EmailMessage
from bayesmail import preprocessing as prep


class CleaningTests(unittest.TestCase):
    def clean(self, body='', subject='主题', content_type='text/plain', label='ham', raw=None, overrides=None):
        self.assertTrue(hasattr(prep, 'clean_email'), '缺少经审计的清洗入口 clean_email')
        if raw is None:
            raw = (f'Subject: {subject}\nContent-Type: {content_type}; charset=utf-8\n\n{body}').encode()
        return prep.clean_email(raw, '000/001', label, overrides or {})

    def test_html_hides_metadata_and_separates_words(self):
        r = self.clean('<html><head><title>hidden title</title></head><body><p>优惠</p><p>活动 &amp; 服务</p><script>hidden()</script><!--secret--></body></html>',content_type='text/html')
        self.assertEqual(r['body'], '优惠 活动 & 服务')
        self.assertEqual(r['status'], 'keep')

    def test_misdeclared_html_and_literal_angle_brackets(self):
        r=self.clean('讨论<信号与系统>：x < 3；<div>甲</div><div>乙</div>')
        self.assertEqual(r['body'],'讨论<信号与系统>：x < 3； 甲 乙')
        self.assertEqual(self.clean('STL <vector> 与 <signal>')['body'],'STL <vector> 与 <signal>')

    def test_damage_does_not_join_words_or_drop_mail(self):
        r=self.clean('hello\ufffdworld\x01尾部')
        self.assertEqual(r['body'],'hello world 尾部')
        self.assertIn('replacement_character',r['quality_flags'])
        self.assertEqual(r['status'],'keep')

    def test_empty_body_keeps_subject_and_empty_text_is_excluded(self):
        r=self.clean(' \n\t')
        self.assertEqual(r['status'],'keep')
        self.assertIn('subject_only',r['actions'])
        self.assertEqual(self.clean('!!!',subject='\ufffd')['status'],'exclude')

    def test_attachment_not_used_and_empty_plain_falls_back_to_html(self):
        m=EmailMessage();m['Subject']='主题';m.set_content(' ')
        m.add_alternative('<p>有效正文</p>',subtype='html');m.add_attachment('不要读取',filename='secret.txt')
        r=self.clean(raw=m.as_bytes())
        self.assertEqual(r['body'],'有效正文')

    def test_exact_flat_alternative_is_not_counted_twice(self):
        self.assertEqual(self.clean('hello world\n<html><body><p>hello world</p></body></html>')['body'],'hello world')
        self.assertEqual(self.clean('说明\n<html><body>不同内容</body></html>')['body'],'说明 不同内容')

    def test_bad_base64_fallback_preserves_chinese(self):
        raw=b'Content-Type: multipart/alternative; boundary=missing\nContent-Transfer-Encoding: base64\nSubject: hi\n\n'+'中文正文'.encode('gbk')
        self.assertEqual(self.clean(raw=raw)['body'],'中文正文')

    def test_reviewed_override_is_hash_guarded_and_label_independent(self):
        raw=b'Subject: hi\n\ngood\nnoise'
        edits={'000/001':{'raw_sha256':hashlib.sha256(raw).hexdigest(),'action':'truncate_body_tail','marker_hex':b'noise'.hex(),'reason':'reviewed binary tail'}}
        a=self.clean(raw=raw,overrides=edits);b=self.clean(raw=raw,overrides=edits,label='spam')
        self.assertEqual(a['body'],'good')
        self.assertEqual(a['body'],b['body'])
        with self.assertRaises(ValueError): self.clean(raw=raw+b'changed',overrides=edits)

    def test_reviewed_subject_repair_and_charset_override(self):
        encoded=base64.b64encode('论坛通知'.encode('gb2312'))
        raw=b'Subject: =?gb2312?B?'+encoded[:4]+b'\n'+encoded[4:]+b'?=\nX-Priority: 3\n\nhello'
        edit={'000/001':{'raw_sha256':hashlib.sha256(raw).hexdigest(),'action':'repair_subject_fold','reason':'reviewed'}}
        r=self.clean(raw=raw,overrides=edit)
        self.assertEqual((r['subject'],r['body']),('论坛通知','hello'))
        raw=b'Subject: =?gb2312?B?'+base64.b64encode('인터넷'.encode('euc-kr'))+b'?=\n\n'
        edit={'000/001':{'raw_sha256':hashlib.sha256(raw).hexdigest(),'action':'subject_charset','charset':'euc-kr','reason':'reviewed'}}
        self.assertEqual(self.clean(raw=raw,overrides=edit)['subject'],'인터넷')

    def test_suspect_binary_is_quarantined_not_silently_kept(self):
        r=self.clean('正常文字 JFIF\x00\x01\x02')
        self.assertEqual(r['status'],'quarantine')

    def test_grouping_handles_same_body_different_subject_and_conflicts(self):
        self.assertTrue(hasattr(prep,'group_records'),'缺少清洗后分组入口')
        rs=[dict(id=str(i),label=label,subject=s,body=b,status='keep',quality_flags=[]) for i,(label,s,b) in enumerate([
            ('ham','A','same'),('ham','B','same'),('spam','A','same'),('ham','C',''),('ham','D','')])]
        groups=prep.group_records(rs)
        self.assertEqual(rs[0]['content_group_id'],rs[1]['content_group_id'])
        self.assertEqual(rs[0]['content_group_id'],rs[2]['content_group_id'])
        self.assertNotEqual(rs[3]['content_group_id'],rs[4]['content_group_id'])
        self.assertEqual([r['status'] for r in rs],['quarantine']*3+['keep']*2)
        self.assertTrue(any(g['cross_label'] for g in groups))

    def test_pipeline_complete_accounting_and_no_overwrite(self):
        self.assertTrue(hasattr(prep,'run_cleaning'),'缺少全量导出入口')
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'data';(root/'full').mkdir(parents=True);(root/'data/000').mkdir(parents=True)
            (root/'full/index').write_text('ham ../data/000/001\nspam ../data/000/002\n')
            a=root/'data/000/001';a.write_bytes(b'Subject: hello\n\nworld')
            (root/'data/000/002').write_bytes(b'Subject: \n\n')
            original=a.read_bytes();out=Path(t)/'out'
            prep.run_cleaning(root,out,{})
            s=json.loads((out/'summary.json').read_text())
            self.assertEqual(s['status_counts'],{'keep':1,'exclude':1})
            self.assertEqual(len((out/'records.jsonl').read_text().splitlines()),2)
            self.assertEqual(len((out/'cleaned.jsonl').read_text().splitlines()),1)
            self.assertEqual(a.read_bytes(),original)
            with self.assertRaises(FileExistsError): prep.run_cleaning(root,out,{})

    def test_html_implicit_head_closure_preserves_visible_body(self):
        r=self.clean('<html><head><title>Title</title><body><p>Real visible message</p></body></html>',content_type='text/html')
        self.assertEqual(r['body'],'Real visible message')

    def test_plain_recognized_tag_placeholders_are_not_html(self):
        r=self.clean('Use <a> as a placeholder and <b> as another.')
        s=self.clean('Use <a> as a placeholder and <i> as another.',label='spam')
        self.assertEqual(r['body'],'Use <a> as a placeholder and <b> as another.')
        prep.group_records([r,s])
        self.assertNotEqual(r['content_group_id'],s['content_group_id'])
        self.assertEqual((r['status'],s['status']),('keep','keep'))

    def test_strict_subject_fold_repair_generalizes_without_edit_list(self):
        encoded=base64.b64encode('论坛通知'.encode('gb2312'))
        raw=b'Subject: =?gb2312?B?'+encoded[:4]+b'\n'+encoded[4:]+b'?=\nX-Priority: 3\n\nhello'
        r=self.clean(raw=raw)
        self.assertEqual((r['subject'],r['body']),('论坛通知','hello'))
        self.assertIn('strict_subject_fold_repair',r['actions'])
        body=b'Subject: =?gb2312?B?'+encoded[:4]+b'\n'+encoded[4:]+b'?=\nX-Priority: 3'
        quoted=self.clean(raw=b'Subject: quote\n\n'+body)
        self.assertNotIn('strict_subject_fold_repair',quoted['actions'])

    def test_grouping_subject_only_and_existing_quarantine(self):
        rs=[dict(id=str(i),label=l,subject=s,body='',status=status,quality_flags=[]) for i,(l,s,status) in enumerate([('ham','same','quarantine'),('spam','same','keep'),('ham','different','keep')])]
        prep.group_records(rs)
        self.assertEqual([r['status'] for r in rs],['quarantine','quarantine','keep'])
        self.assertEqual(rs[0]['content_group_id'],rs[1]['content_group_id'])

    def test_pipeline_rejects_output_in_source_and_stale_audit(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'corpus';(root/'full').mkdir(parents=True);(root/'data/000').mkdir(parents=True)
            (root/'full/index').write_text('ham ../data/000/001\n')
            (root/'data/000/001').write_bytes(b'Subject: hi\n\nworld')
            with self.assertRaises(ValueError):prep.run_cleaning(root,root/'output',{})
            audit=Path(t)/'audit.jsonl';audit.write_text(json.dumps(dict(id='000/001',label='ham',raw_sha256='stale'))+'\n')
            out=Path(t)/'out'
            with self.assertRaises(ValueError):prep.run_cleaning(root,out,{},audit)
            self.assertEqual(json.loads((out/'manifest.json').read_text())['state'],'in_progress')
            self.assertFalse((out/'cleaned.jsonl').exists())

    def test_html_implicit_body_start_preserves_text_but_not_title(self):
        r=self.clean('<html><head><title>Title</title><p>Real visible message</p></html>',subject='',content_type='text/html')
        self.assertEqual((r['body'],r['status']),('Real visible message','keep'))
        r=self.clean('<html><head><title><p>Not body</p></title><style>p{color:red}</style><p>Visible</p></html>',content_type='text/html')
        self.assertEqual(r['body'],'Visible')

    def test_reviewed_unpaired_html_is_cleaned_without_global_placeholder_loss(self):
        raw=b'Subject: hi\n\nFirst<br>Second<P>'
        edits={'000/001':{'raw_sha256':hashlib.sha256(raw).hexdigest(),'action':'force_html','reason':'reviewed legacy HTML breaks'}}
        self.assertEqual(self.clean(raw=raw,overrides=edits)['body'],'First Second')
        self.assertEqual(self.clean('Use <br> to discuss markup')['body'],'Use <br> to discuss markup')
