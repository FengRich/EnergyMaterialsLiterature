# V1.0 验收记录

验证日期为 2026-11-10（北京时间）。托管端验收需在获得公开部署授权后进行。

| 验收项 | 实测结果 |
| --- | --- |
| 期刊标识 | 按 ISSN 查询真实 OpenAlex Sources，匹配到 27 个唯一期刊。核对现行 ISSN-L、纸版与电子版标识，别名不参与匹配。多源标识冲突进入待核验。 |
| 真实论文 | `python -m tests.live_acceptance` 直接按 DOI 获取 42 篇。修订规则后 26 收录、4 待核验、6 拒绝、6 排除，期刊与状态 0 项不符。包括计算方法、AI 交叉、综述、实验对照、缺摘要、刊外和封面记录。 |
| 多源与 DOI | Crossref 和 OpenAlex 各实测分页和 DOI 检索。对同一 JACS DOI 合并两份真实记录，首见时间保留。Semantic Scholar 的批量 DOI 核对有 200 实测，匿名补充也曾返回 429。 |
| 持久化与失败 | 独占锁拒绝重入。上游全失败的自动化回归保留原状态文件的字节内容。发现时间、出版日期和周报归属分别保留。以 36 条真实记录、一份周报和一条人工审核做 Git ZIP 解压并复验。两个写入者并发时，实测拒绝陈旧 Git 推送。 |
| 补跑 | 通过生产同步入口做同周回归，使用受控源响应检验 DOI 和周报幂等。真实回溯与补跑的现场进度单列于 current-progress.md。 |
| 网站与 RSS | 在 Edge 通过 HTTP 子路径以 342 篇正式收录论文检查首页及四个导航页。实测 DOI 搜索、期刊与领域组合过滤、时间排序、详情展开。1365px 桌面截图与 390px 手机检查通过，五页均无横向溢出和 JavaScript 异常。首版 RSS 的三条真实条目均可解析，GUID 唯一，日期有效。 |
| 工作流 | Python 3.14.10 的 22 项自动化测试通过。Actionlint 1.7.12 校验两份工作流。北京时间周一 09:00 对应 UTC 周一 01:00，定时触发配置和手动入口均已检查。 |
| 托管端 | GitHub Pages 的公开访问、实际定时触发和自动部署待授权后验收。 |

本地浏览器验收使用从真实 API 获取的专用样本，周报归属用于测试页面和排序。抽样结果只说明本组样本。检索完整性受出版方索引时差、上游速率限制、摘要可用性与规则精度影响。

```sh
python -m unittest discover -s tests -v
python -m tests.live_acceptance --preview-state .work/acceptance-preview.json
python -m energy_lit --state .work/acceptance-preview.json build --output dist
python -m http.server 8000 --bind 127.0.0.1 --directory dist
playwright-cli -s=energy-lit-qa open http://127.0.0.1:8000/ --browser=msedge
playwright-cli -s=energy-lit-qa run-code --filename tests/browser.cjs
playwright-cli -s=energy-lit-qa close
```
