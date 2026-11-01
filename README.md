# BayesMail

简单的 Python 朴素贝叶斯垃圾邮件分类课程作业。

## 当前状态

已实现邮件读取、异常样本复核、版本化清洗、清洗后查重，以及按内容组划分、训练词表和手写多项式朴素贝叶斯。全流程使用 Python 标准库，不改动原始数据。

- 清洗规则与复现：[docs/cleaning_rules_v1.md](docs/cleaning_rules_v1.md)
- 清洗质量报告保存在本地 `reports/cleaning_v1_verified/REPORT.md`，不随公开仓库发布。
- 下游输入：`reports/cleaning_v1_verified/cleaned.jsonl`，仅包含 keep 状态邮件；按 `content_group_id` 分组划分。
- 训练产物：`reports/training_v1/`，含训练/测试集、训练词表、模型、摘要和可校验清单。
- 审计记录及隔离样本分别见该目录 `records.jsonl`、`quarantine.jsonl`；数据与报告产物默认不纳入版本控制。

## 最终评估结果

2026-11-01 在本地使用冻结的 `reports/training_v1/test.jsonl` 和 `reports/training_v1/model.json` 重新评估；原始邮件、测试集、模型及误分类明细均未上传到公开仓库。以垃圾邮件为正类，13,095 封测试邮件中正常邮件 4,311 封、垃圾邮件 8,784 封：

| 指标 | 结果 |
| --- | ---: |
| 准确率 | 93.72% |
| 垃圾邮件精确率 | 96.53% |
| 垃圾邮件召回率 | 94.01% |
| 垃圾邮件 F1 | 95.25% |
| 正常邮件误判率 | 6.89% |

| 实际类别 | 预测正常 | 预测垃圾 |
| --- | ---: | ---: |
| 正常邮件 | 4,014 | 297 |
| 垃圾邮件 | 526 | 8,258 |

共误分类 823 封。评估命令如下，输出目录须使用尚不存在的路径：

```bash
PYTHONPATH=src python3 -m bayesmail.evaluate \
  reports/training_v1/test.jsonl reports/training_v1/model.json \
  --output reports/evaluation_20261101
```

本次另运行 `PYTHONPATH=src python3 -m unittest discover -s tests -v`，58 个测试通过。仓库不包含数据和模型文件，因此这些指标需要在取得相同冻结产物后才能独立复现。

## 清洗与重新查重（WSL / Linux，Python 3.10+）

```bash
PYTHONPATH=src python3 -m bayesmail.preprocessing data/trec06c \
  --output reports/cleaning_v1_verified \
  --overrides docs/cleaning_overrides_v1.json \
  --source-audit reports/full_quality_20260920T134535Z/records.jsonl
python3 reports/verify_cleaning.py reports/cleaning_v1_verified
```

输出目录不可覆盖；重跑请使用新目录。只有 `manifest.json` 中 state 为 complete 且独立验证通过的结果可供下游使用。`reports/cleaning_v1` 与 `reports/cleaning_v1_final` 是已废弃的开发产物，不可用于划分。

## 读取邮件（WSL / Linux，Python 3.10+）

按 data/README.md 放好数据，在项目根目录运行：

```bash
PYTHONPATH=src python3 -m bayesmail.data data/trec06c --per-class 10 --output reports/email_samples.jsonl
```

输出正常邮件、垃圾邮件各 10 封。文件为 UTF-8 JSONL，每行一封邮件：

```json
{"id":"000/001","label":"ham","subject":"会议通知","body":"请参加会议"}
```

检查 subject、body 是否乱码、为空或包含异常内容。解码无法完整恢复时会发出警告。
输出文件已存在时不会覆盖，请换一个输出文件名。
样本不足、索引格式错误、路径越界或选中邮件缺失时，命令会报错。
本命令只检查读取到的索引前缀和选中邮件，不代表全量数据检查通过。

## 测试

测试使用临时合成邮件，不依赖下载数据：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 目录

- src/bayesmail/email_parser.py：统一的 MIME、编码和 HTML 正文解析。
- src/bayesmail/cleaning.py：单封邮件修复、归一化和质量判定。
- src/bayesmail/grouping.py：内容哈希、重复分组和跨标签冲突处理。
- src/bayesmail/artifacts.py：JSON/JSONL、哈希和运行产物公共设施。
- src/bayesmail/data.py：数据读取和抽样命令编排。
- src/bayesmail/preprocessing.py：清洗、分组和产物生成命令编排。
- src/bayesmail/model.py：分词、训练词表和多项式朴素贝叶斯。
- src/bayesmail/train.py：按内容组分层划分并生成可审计训练产物。
- src/bayesmail/evaluate.py：冻结测试集评估和误分类记录。
- data/：本地数据及格式说明。
- tests/：邮件读取、清洗、分组划分和模型测试。
- reports/：抽样结果与后续实验报告。
- docs/references.md：参考资料。

## 后续步骤

重点检查正常邮件被误判为垃圾邮件的案例。测试集不得用于调整词表或模型参数。
