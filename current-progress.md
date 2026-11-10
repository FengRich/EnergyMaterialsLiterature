# 开发进度

## 当前阶段

Phase 5 本地验收通过。初始回溯从 2026-08-10 开始，两源一度同时失败，随后从 1,782 条检查点接续到 2026-11-08，再同步本周数据。初始同步保存 2,087 条。真实同周补跑后保存 2,090 条，其中 343 Accepted、1,173 Pending、574 Rejected。所有原有记录和首见时间保留，DOI 唯一，一份周报，三条 RSS 代表论文。最新成功同步起始时间为 2026-11-10 16:18（北京时间）。

## 已完成

- Phase 0。四仓源码审查，两候选在隔离环境运行原有测试及真实检索，选择 B。详见 docs/open-source-evaluation.md。
- Phase 1–2。27 刊标识与三源接口，源故障隔离，DOI 合并，重叠同步，三态筛选、人工审核、撤稿和摘要授权。
- Phase 3。首页、静态文献库、周报、待核验、About 和 RSS。以正式数据在 Pages 风格子路径验证五个页面、搜索筛选、桌面和 390px 手机布局。
- Phase 4。Actions 计划与手动入口、写锁、校验、Git 快进、快照。实测拒绝陈旧推送，恢复真实记录、周报和人工审核。
- Phase 5。42 篇真实 DOI 的期刊与筛选预期全部匹配。真实 DOI 跨源合并和 Semantic Scholar 核对成功。Python 3.14.10 的 22 项自动化测试和 actionlint 1.7.12 工作流校验通过。详见 docs/acceptance.md。

## READY

- 本地交付已准备。获得公开授权后，创建指定 GitHub 仓库、配置 Actions Pages、执行手动同步和首次发布，随后检查 HTTPS、调度和 RSS。

## BLOCKED

- 公开建仓、Pages 部署、托管端实际定时触发与公开可访问性验收需要用户授权。
- OpenAlex 匿名限流影响 2026-10-19 至 2026-11-08 的三段历史查询与最近两次同步。Crossref 和 Semantic Scholar 已成功，后续同步会逐批重试缺段。网站会展示异常。

## 恢复

生产路径使用 `python -m energy_lit sync`，本地页面由 `python -m energy_lit build` 生成。同步中断时，保留上一验证状态和已完成的初始回溯检查点。仅确认进程已退出后处理残留锁。运行与恢复见 docs/operations.md。
