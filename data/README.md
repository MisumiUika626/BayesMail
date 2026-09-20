# 数据

第一阶段使用 TREC06C 中文邮件语料。本地已下载教学镜像；原始邮件不纳入 Git。下载来源与 SHA-256 记录在 data/download_source.json。镜像压缩包不含许可说明，未核验与原版逐字节一致。
请从 TREC 数据入口获取语料并核对随包说明和使用条款：
https://trec.nist.gov/data/spam.html

解压后建议放置为：

```text
data/trec06c/
  full/index
  data/000/000
  data/000/001
  ...
```

命令接收包含 `full/` 和 `data/` 的那一层目录；如果解压后有双层 trec06c，请相应调整路径。
索引每行是标签与相对于 full/ 的路径，例如：

```text
spam ../data/000/000
ham ../data/000/001
```

标签：spam 为垃圾邮件，ham 为正常邮件。读取器输出 id、label、subject、body。
主题和正文优先按声明编码解码，再尝试 UTF-8、GB18030；均失败时会警告并保留替代字符。
MIME 邮件优先选择纯文本正文，否则提取 HTML 可见文本，忽略附件。
这一步不分词、不划分训练集，也不会执行邮件中的脚本。

数据文件默认不提交到 Git。抽样按索引顺序各取前 10 封，仅用于人工检查，不能用作正式评估集。
