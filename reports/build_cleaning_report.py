"""Render a human-readable report from verified cleaning artifacts."""
import json
from pathlib import Path
from collections import Counter,defaultdict

O=Path(__file__).resolve().parent/'cleaning_v1_verified'
s=json.loads((O/'summary.json').read_text())
v=json.loads((O/'verification.json').read_text())
assert v['status']=='passed'
rs=[json.loads(x) for x in (O/'records.jsonl').read_text().splitlines()]
q=[r for r in rs if r['status']=='quarantine']
bylabel=defaultdict(Counter)
for r in q:
 for flag in r['quality_flags']:
  if flag in ('unresolved_subject_encoding','suspected_binary','review_pending','cross_label_content_group'):
   bylabel[flag][r['label']]+=1
lines=['# 数据清洗与重新查重报告（clean-v1）','',
'本轮完成清洗与重新查重。原始邮件不变；未划分训练/测试集，未训练模型。正式目录为 `reports/cleaning_v1_verified`，其他 cleaning_v1 开发目录已标为 superseded。','',
'## 数据处置','',
'| 类别 | 原始邮件 | 保留 keep | 隔离 quarantine | 排除 exclude |',
'|---|---:|---:|---:|---:|']
for label in ('ham','spam'):
 c=s['by_label'][label]
 lines.append(f"| {label} | {sum(c.values()):,} | {c.get('keep',0):,} | {c.get('quarantine',0):,} | {c.get('exclude',0):,} |")
c=s['status_counts']
lines += [f"| 合计 | {s['total']:,} | {c.get('keep',0):,} | {c.get('quarantine',0):,} | {c.get('exclude',0):,} |",'',
'每封原邮件都保留在 records.jsonl 中。隔离和排除仅表示不进入 cleaned.jsonl，未删除源文件；同内容的合格重复邮件仍保留。','',
'## 清洗前后','', '| 指标（全部邮件） | 清洗前 | 清洗后 |','|---|---:|---:|']
for key,label in [('empty_body','空正文'),('replacement_character','含 U+FFFD'),('residual_html_heuristic','疑似 HTML 标签')]:
 lines.append(f"| {label} | {s['before'][key]:,} | {s['after'][key]:,} |")
lines += ['',
'替代字符转换成分隔空格，计数下降不代表原文字已恢复；损坏与私用区字符标记仍保留。HTML 指标采用本轮扩展标签集合（含 a/span/img 等），所以清洗前数量与旧报告 149 的窄口径不同。零命中不代表完备的 HTML/乱码检测。',
'',f"- 主题头严格折行修复：自动 {s['actions'].get('strict_subject_fold_repair',0)} 封，加原先复核的 149/033 共 {s['actions'].get('strict_subject_fold_repair',0)+1} 封；不修复缺乏严格解码证据的主题。",
f"- HTML 可见文本提取：{s['actions'].get('html_visible_text',0):,} 封；其中13封孤立标签样本有独立哈希限定复核记录。",
f"- 空正文保留主题：{s['actions'].get('subject_only',0)} 封；包括4封正常邮件。",
f"- 完全相同的扁平纯文本/HTML双版本合并：{s['actions'].get('identical_flat_alternative_removed',0)} 封；不能证明相同的 {s['actions'].get('mixed_plain_html_preserved',0)} 封保留并标记。",
'- 008/280：保留影评，截去已定位的图片尾部；211/231：仅将该主题按 EUC-KR 恢复；161/281：损坏退信继续隔离。',
'', '## 隔离原因','', '| 主要原因 | ham | spam |','|---|---:|---:|']
for flag,labels in sorted(bylabel.items()):lines.append(f"| {flag} | {labels['ham']} | {labels['spam']} |")
lines += ['', '原因可能重叠，不能一概相加。详见 quarantine.jsonl 和 quarantine_index.md。当前主要是未可靠恢复的编码主题；隔离比例在两类间不同，后续结果应说明适用的是保留子集，不是宣称原语料完全无损坏。',
'', '## 清洗后重复组','', '| 口径 | 重复组 | 组内邮件 | 每组只留1封的冗余 | 跨标签组 |','|---|---:|---:|---:|---:|']
for kind,label in [('subject_body','主题＋正文'),('body','非空正文（主题可不同）')]:
 d=s['duplicates'][kind];lines.append(f"| {label} | {d['groups']:,} | {d['records_in_groups']:,} | {d['excess_records']:,} | {d['cross_label_groups']} |")
lines += ['',f"归一化主题＋正文的唯一内容数从 {s['original_unique_subject_body']:,} 变为 {s['cleaned_unique_subject_body']:,}。哈希和组成员已重新计算，未沿用旧审计分组。",
f"可用于后续划分的 keep 邮件共有 **{s['eligible_content_groups']:,} 个 content_group_id**。同一非空正文即使主题不同也必须进入同一集合；空正文按主题＋正文分组。", 
'两种重复口径相互重叠，不能相加。没有检测所有语义近重复；不同正文仍可能是同一模板的小变体。','',
'## 验证证据','',f"- {v['raw_hashes_verified']:,} 封原文件 SHA-256 在生成时与此前全量审计逐封匹配，生成后再次独立匹配；原始索引一致。",
'- 独立验证每个 ID 恰好对应一条总记录、状态文件完整互斥、清洗哈希可重算、重复组成员及标签计数一致。',
'- 独立检查四个特殊个案的实际输出，并核对正式产物与代码哈希。',
'- 29 项解析/清洗测试通过；覆盖普通尖括号文本、HTML隐式头结束、字符损坏分隔、附件排除、空正文、修复哈希保护、跨标签隔离和输出覆盖保护。','',
'## 下一步','',
'以 cleaned.jsonl 中的 content_group_id 为单位做可复现的训练/测试划分，检查两边组 ID 交集为空；记录随机种子、类别比例及各类邮件/组数量。之后才在训练集建立词表并训练朴素贝叶斯。质量标记、原始路径和 ID 不作为文本特征。',
'', '规则与重跑命令见 ../../docs/cleaning_rules_v1.md；机器可读统计见 summary.json，验证证据见 verification.json。','']
(O/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
def escape(s):return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('|','\\|').replace('\n',' ')
lines=['# 待复核隔离清单','',f'共 {len(q)} 封，原文件未删除。恢复或调整规则后必须重新清洗和计算组。','', '| ID | 类别 | 主题 | 原因 |','|---|---|---|---|']
for r in q:
 reasons=[f for f in r['quality_flags'] if f in bylabel]
 lines.append(f"| {r['id']} | {r['label']} | {escape(r['subject'])} | {', '.join(reasons)} |")
(O/'quarantine_index.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(O/'REPORT.md')
