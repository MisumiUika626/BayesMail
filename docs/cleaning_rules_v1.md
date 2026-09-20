# 邮件清洗规则 clean-v1

本轮承接异常复核表，只清洗、记录处置并重新查重，不做划分、分词、词表拟合或训练。原始邮件不可变，输出目录已存在即拒绝覆盖；manifest.state 为 complete 且独立验证通过后才能进入下一步。

## 规则

- 在真正头区域（首个空行之前），仅当唯一一处 Subject encoded-word 无缩进折行的两段拼接可严格 base64 和声明字符集解码、且后面跟合法头字段时恢复折行；其他不确定头保留隔离。不修复正文里引用的头字段。
- 字符解码沿用读取器的声明字符集→UTF-8→GB18030及最少替代字符回退。base64 严格校验失败时使用原始扁平载荷；缺边界 multipart 回退读取正文。附件不进入文本，空纯文本允许回退同邮件 HTML 版本。
- 已声明 HTML 或含成对已知标签、带属性标签或独立 br/hr 行的正文使用解析器取可见文本，移除 head/title/script/style/注释，保留段落分隔、可见链接文字和未知尖括号表达式；不访问邮件链接或运行脚本。不进行通用 `<...>` 正则删词。
- 纯文本前缀与完整 HTML 后缀的可见文字经相同归一化后完全相同时，只保留一个版本。不能证明一致的拼接保留并标记 mixed_plain_html_preserved；不删普通重复句子。
- NFC、空白折叠；U+FFFD、控制字符和格式字符转换成空格，避免词粘连。不转小写、不删标点、不猜缺字。替代字符变少只说明分隔处理，不能称为成功恢复乱码。原始质量标记和替代字符数量保留。
- 正文为空且主题可用时保留主题；主题与正文都没有 Unicode 字母/数字时，状态为 exclude，原文仍保留。没有按标签删除异常邮件的规则。
- NUL、至少8个异常控制字符、带控制字符的 JFIF 或未解开的 encoded-word 主题，进入 quarantine。阈值是保守隔离准则，不是乱码完备检测器；私用区字符标记而不一概删除。
- docs/cleaning_overrides_v1.json 为17个已审阅的个案记录（四个特殊样本及13个遗留HTML样本），含 ID、原文 SHA-256、动作和理由。原文不匹配即失败，不套用修复；动作不根据标签变化。008/280 截去图片尾部，149/033 恢复主题头边界，211/231 用 EUC-KR 恢复主题，161/281 暂缓处理；13封孤立 br/P 标签邮件经复核后启用哈希限定的 HTML 提取。新增个案需先复核并发布新规则版本。

## 查重与后续分组

保留所有合格重复邮件，不提前只留一封。normalized_sha256 是 UTF-8 紧凑 JSON `[subject, body]` 的 SHA-256；与旧审计 JSON 序列化格式不同，不可直接比较哈希字符串，只比较组成员或使用本轮 before.normalized_sha256。

同时对非空正文计算 body_sha256，正文完全相同而主题不同的邮件共用 content_group_id；空正文按主题＋正文分组，绝不把所有空正文合成一个大组。content_group_id 用于后续防泄漏划分。当前只查精确归一化重复，没有进行模糊/语义近重复检测。

组内出现 ham/spam 冲突时，保守隔离整个相关内容组，保留两种原标签，不投票改标。正文相同、主题不同未必是标注错误，报告将其视作需要复核的冲突风险。

## 输出

- records.jsonl：每封原始邮件对应一条清洗文本及处置记录，含 ID/原始哈希/版本/动作/质量标记/原解析统计/各内容哈希。
- cleaned.jsonl：仅 keep，可作为后续按组划分的输入；质量字段不得直接作为分类特征。
- quarantine.jsonl：待复核记录；excluded.jsonl：无有效文本记录。
- duplicate_groups.jsonl：主题＋正文以及非空正文重复组，含成员与标签计数。这两种口径的数量不可相加。
- summary.json、manifest.json、reviewed_overrides.json：汇总、代码和产物哈希、运行状态、冻结的个案规则。
- verification.json：独立重新核对数量、原文件哈希、重复组和个案输出的结果。

## 复现

在项目根目录运行，输出使用新的目录名：

```bash
PYTHONPATH=src python3 -m bayesmail.preprocessing data/trec06c \
  --output reports/cleaning_v1_verified \
  --overrides docs/cleaning_overrides_v1.json \
  --source-audit reports/full_quality_20260920T134535Z/records.jsonl
python3 reports/verify_cleaning.py reports/cleaning_v1_verified
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

对其他数据集可省略 overrides 和 source-audit。失败运行目录保留 in_progress 状态以便诊断，不能交给下游；改用新目录重跑。规则实现、特殊个案和输入变化后都应重新运行并验证，不能沿用旧组。

本轮首轮开发产物 reports/cleaning_v1 已标记 superseded；最终目录为 reports/cleaning_v1_verified。
