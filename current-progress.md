# 开发进度

## 当前阶段

Phase 5 已完成首次公开部署及线上验收。2026-11-10 16:51（北京时间）的手动运行保存 2,106 条记录，其中 348 Accepted、1,172 Pending、586 Rejected。同步、构建和部署均通过，工作流已生成可恢复快照。公开页面、静态资源和 RSS 均返回 HTTPS 200。

[GitHub Pages](https://fengrich.github.io/EnergyMaterialsLiterature/) · [RSS](https://fengrich.github.io/EnergyMaterialsLiterature/feed.xml) · [手动运行记录](https://github.com/FengRich/EnergyMaterialsLiterature/actions/runs/42785837428)

## 已完成

- Phase 0。四仓源码审查，两候选在隔离环境运行原有测试及真实检索，选择 B。详见 docs/open-source-evaluation.md。
- Phase 1–2。27 刊标识与三源接口，源故障隔离，DOI 合并，重叠同步，三态筛选、人工审核、撤稿和摘要授权。
- Phase 3。首页、静态文献库、周报、待核验、About 和 RSS。以正式数据在 Pages 风格子路径验证五个页面、搜索筛选、桌面和 390px 手机布局。
- Phase 4。Actions 计划与手动入口、写锁、校验、Git 快进、快照。实测拒绝陈旧推送，恢复真实记录、周报和人工审核。
- Phase 5。42 篇真实 DOI 的期刊与筛选预期全部匹配。真实 DOI 跨源合并和 Semantic Scholar 核对成功。Python 3.14.10 的 22 项自动化测试和 actionlint 1.7.12 工作流校验通过。详见 docs/acceptance.md。

## 后续运行

- 每周一北京时间 09:00 运行，保留手动入口。线上已验证手动触发，首次定时触发可在 Actions 运行历史中核对。
- 最新手动运行的 Crossref、OpenAlex 和 Semantic Scholar 均成功。OpenAlex 的 2026-10-26 至 2026-11-01 历史区间仍受 HTTP 429 影响，后续同步会重试，首页保留提示。

## 恢复

生产路径使用 `python -m energy_lit sync`，本地页面由 `python -m energy_lit build` 生成。同步中断时，保留上一验证状态和已完成的初始回溯检查点。仅确认进程已退出后处理残留锁。运行与恢复见 docs/operations.md。
