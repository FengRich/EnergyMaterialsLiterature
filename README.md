# AI & Computational Energy Materials Literature Hub

AI 电化学能源材料顶刊文献情报系统。每周跟踪 27 本期刊中的电池、电催化、电解液计算研究，生成文献库、代表论文、周报、待核验目录和 RSS。

## 本地运行

使用 `.python-version` 中的 Python 版本。运行时使用 Python 标准库，最低 Python 3.13。默认状态文件为 `data/state.json`。

```sh
python -m unittest discover -s tests -v
python -m energy_lit validate
python -m energy_lit sync
python -m energy_lit build
python -m http.server 8000 --bind 127.0.0.1 --directory dist
```

首次同步从北京时间当前日期回溯三个日历月，按七日批次保存已验证进度。同步中断后重跑会读取同一路径旁的 `state.bootstrap.json`。后续使用重叠窗口。报告按北京时间周一 09:00 开版，同周补跑更新该版，实际发现日期和出版日期各自保留。历史回溯记录不计入首版新增。

`--state PATH` 放在子命令前可指定独立数据文件。Crossref、OpenAlex 与 Semantic Scholar 支持匿名运行。可在授权后通过相应环境变量提供 Crossref 联系地址和免费 API key。部署与恢复见 [运维手册](docs/operations.md)。

## 人工审核

编辑 `config/reviews.json`，以小写 DOI 为键，每条记录含 `decision`（`Accepted`、`Pending` 或 `Rejected`）、`reason`、HTTPS `evidence` 和 ISO `date`。下一次同步应用决定。Accepted 仍要求可验证的白名单期刊、标题、DOI，且未标记撤稿。人工 Pending 的理由会公开显示。

`config/abstract-licenses.json` 记录经核验可公开转载的摘要，每条含数据源 `source`、原文标准化后的 `sha256`、`license`、HTTPS `evidence` 和审核 `date`。公开条件绑定 DOI、数据源与准确文本。授权证据必须明确覆盖该摘要。未确认授权的摘要只在运行内存中用于筛选。权重和关键词见 `config/rules.json`。

## 数据与代码

元数据来自 Crossref、OpenAlex 和 Semantic Scholar。白名单中的 OpenAlex 期刊 ID、ISSN-L、已登记 ISSN 和历史别名来自 OpenAlex Sources。匹配使用标识，别名供核验参考。Angewandte Chemie 的历史英文版 ISSN 0570-0833 与现行 ISSN-L 1433-7851 分列，首版使用现行期刊标识。Energy Storage Materials 的 2405-8297 为印刷版，2405-8289 为网络版。 [ISSN 国际中心](https://portal.issn.org/resource/issn/0570-0833) · [现行国际版](https://portal.issn.org/resource/ISSN-L/1433-7851) · [Energy Storage Materials](https://portal.issn.org/resource/ISSN/2405-8297)项目保留源内状态与每篇论文的来源信息。公开页面和订阅仅展示元数据及获准摘要。全文和 PDF 由出版方提供。

复用的 MIT 源文件来自 [Paper Digest](https://github.com/X-PG13/paper-digest/tree/8ed7900a68b4436cded7e35c6986da4b90ea2758)，版权和条款在 `energy_lit/LICENSE.paper-digest`。
