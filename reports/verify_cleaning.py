"""Independent artifact/accounting verification. Run: python3 reports/verify_cleaning.py OUTPUT."""
import argparse
import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def key(value):
    return sha(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())


def read_rows(path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]


def verify(out):
    out=Path(out).resolve()
    manifest=json.loads((out/'manifest.json').read_text())
    summary=json.loads((out/'summary.json').read_text())
    assert manifest['state']=='complete', 'Incomplete run'
    project=Path(__file__).resolve().parents[1]
    assert sha((project/'src/bayesmail/preprocessing.py').read_bytes())==manifest['cleaner_sha256']
    assert sha((project/'src/bayesmail/data.py').read_bytes())==manifest['parser_sha256']
    for name,expected in manifest['artifact_sha256'].items():
        assert sha((out/name).read_bytes())==expected, name
    rows=read_rows(out/'records.jsonl')
    ids={r['id'] for r in rows}
    assert len(rows)==len(ids)==summary['total']
    root=Path(manifest['root'])
    indexed={}
    for line in (root/'full/index').read_text().splitlines():
        if line.strip():
            label,relative=line.split()
            id=relative.removeprefix('../data/')
            assert id not in indexed
            indexed[id]=label
    assert ids==set(indexed)
    assert sha((root/'full/index').read_bytes())==manifest['index_sha256']
    by_id={r['id']:r for r in rows}
    for name,status in [('cleaned','keep'),('quarantine','quarantine'),('excluded','exclude')]:
        subset=read_rows(out/(name+'.jsonl'))
        assert len(subset)==len({r['id'] for r in subset})
        assert {r['id'] for r in subset}=={r['id'] for r in rows if r['status']==status}
        assert all(r==by_id[r['id']] for r in subset)
    assert dict(Counter(r['status'] for r in rows))==summary['status_counts']
    for label in ('ham','spam'):
        assert dict(Counter(r['status'] for r in rows if r['label']==label))==summary['by_label'][label]
    actual_groups={'subject_body':defaultdict(list),'body':defaultdict(list)}
    leakage=defaultdict(list)
    for i,r in enumerate(rows,1):
        assert r['label']==indexed[r['id']]
        assert sha((root/'data'/r['id']).read_bytes())==r['raw_sha256'], r['id']
        assert r['normalized_sha256']==key([r['subject'],r['body']])
        assert r['body_sha256']==(key(r['body']) if r['body'] else None)
        for field in ('subject','body'):
            text=r[field]
            assert '\ufffd' not in text
            assert not any(unicodedata.category(c) in ('Cc','Cf') for c in text)
            assert text==' '.join(text.split())
        if r['status']!='exclude':
            expected=key(['body',r['body_sha256']]) if r['body'] else key(['subject_only',r['normalized_sha256']])
            assert r['content_group_id']==expected
            leakage[expected].append(r)
            actual_groups['subject_body'][r['normalized_sha256']].append(r['id'])
            if r['body']:
                actual_groups['body'][r['body_sha256']].append(r['id'])
        if i%10000==0: print(f'Verified {i}/{len(rows)} raw hashes',flush=True)
    groups=read_rows(out/'duplicate_groups.jsonl')
    assert len(groups)==len({(g['kind'],g['sha256']) for g in groups})
    for kind,mapping in actual_groups.items():
        expected={k:set(v) for k,v in mapping.items() if len(v)>1}
        reported={g['sha256']:set(g['members']) for g in groups if g['kind']==kind}
        assert expected==reported
        s=summary['duplicates'][kind]
        assert s['groups']==len(expected)
        assert s['records_in_groups']==sum(map(len,expected.values()))
        assert s['excess_records']==sum(len(v)-1 for v in expected.values())
        assert s['cross_label_groups']==sum(len({by_id[i]['label'] for i in v})>1 for v in expected.values())
    for g in groups:
        labels=Counter(by_id[i]['label'] for i in g['members'])
        assert dict(labels)==g['labels']
        assert g['cross_label']==(len(labels)>1)
        if g['cross_label']: assert all(by_id[i]['status']=='quarantine' for i in g['members'])
    for rs in leakage.values():
        assert len({r['label'] for r in rs if r['status']=='keep'})<=1
    assert summary['eligible_content_groups']==len({r['content_group_id'] for r in rows if r['status']=='keep'})
    # Fixed reviewed outputs, independent from production implementation.
    if {'008/280','149/033','211/231','161/281'}<=ids:
        assert 'JFIF' not in by_id['008/280']['body'] and '被感动了一回' in by_id['008/280']['body']
        assert by_id['149/033']['subject']=='● [论坛22日晚]国际管理咨询协会理事会(ICMCI)-清华管理咨询论坛'
        assert 'X-Priority' not in by_id['149/033']['body']
        assert by_id['211/231']['subject']=='25배 빠른 초고속인터넷 - 파워콤'
        assert by_id['211/231']['body']==''
        assert by_id['161/281']['status']=='quarantine'
    result=dict(status='passed',records=len(rows),raw_hashes_verified=len(rows),
                complete_status_partition=True,duplicate_groups_recomputed=True,
                cross_label_groups_quarantined=True,reviewed_examples_checked=True,
                manifest_sha256=sha((out/'manifest.json').read_bytes()),verifier_sha256=sha(Path(__file__).read_bytes()))
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output');verify(p.parse_args().output)
