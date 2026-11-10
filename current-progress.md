# 开发进度

## 当前阶段

Phase 5 本地验收。已完成真实三个月初始化并构建本地站点。初次回溯在两源故障后从 1,782 条检查点恢复，回溯至 2026-11-08，再同步本周记录。首次成功保存 2,087 条候选记录，其中 342 Accepted、1,173 Pending、572 Rejected，生成一份周报和三条 RSS 代表论文。

## 已完成

- Phase 0。四仓源码审查，两候选在隔离环境运行原有测试及真实检索，选择 B。详见 docs/open-source-evaluation.md。
- Phase 1–2。27 刊标识与三源接口，源故障隔离，DOI 合并，重叠同步，三态筛选、人工审核、撤稿和摘要授权。
- Phase 3。首页、静态文献库、周报、待核验、About 和 RSS。以正式数据在 Pages 风格子路径验证五个页面、搜索筛选、桌面和 390px 手机布局。
- Phase 4。Actions 计划与手动入口、写锁、校验、Git 快进、快照。实测拒绝陈旧推送，恢复真实记录、周报和人工审核。
- Phase 5。42 篇真实 DOI 的期刊与筛选预期全部匹配，真实 DOI 跨源合并与 Semantic Scholar 核对成功。Python 3.14.10 通过 22 项自动化测试，actionlint 1.7.12 检查两份工作流。详见 docs/acceptance.md。

## READY

- 等待同周真实补跑完成，核对首见时间、DOI、周报与状态。
- 发布前复核 API 受限状态并准备最后一个可恢复快照。

## BLOCKED

- OpenAlex 匿名限流影响 10 月 19 日至 11 月 8 日的三段历史查询与最新一次查询。Crossref 初始数据和 Semantic Scholar 补充已成功，下一次同步继续尝试恢复缺段。
- 公开创建 GitHub 仓库、启用 Pages、首次正式部署、托管端自动触发和可访问性验证需要用户授权。

## 恢复

生产路径使用 `python -m energy_lit sync`。本轮隔离补跑使用 `.work/live-state.json`。同步中断时，保留上一验证状态和已完成的初始回溯检查点。仅确认进程已退出后处理残留锁。运行与恢复见 docs/operations.md。
