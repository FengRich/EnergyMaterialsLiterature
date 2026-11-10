# 开发进度

## 当前阶段

Phase 5 本地验收。Phase 0–4 实现已落在此独立 Git 项目。实时初始回溯曾在 2026-10-26 批次遇到两源故障，前 11 个批次保存了 1,782 条记录；已以原检查点重跑接续。

## 已完成

- Phase 0。四仓源码审查，两候选在隔离环境运行原有测试及真实检索，选择 B。详见 docs/open-source-evaluation.md。
- Phase 1–2。27 刊标识与三源接口，源故障隔离，DOI 合并，重叠同步，三态筛选，人工审核，撤稿和按 DOI、源、摘要哈希授权。
- Phase 3。首页、静态文献库、周报、待核验、About 和 RSS。本地以 GitHub Pages 子路径测试桌面、390px 手机布局和交互。
- Phase 4。编排、锁、校验、Git 快进写入、快照与回滚手册。支持 IANA 时区的 actionlint 1.7.12 校验通过。以 36 条真实记录、一份周报和一条 DOI 人工审核完成 Git ZIP 快照恢复。
- Phase 5。42 篇真实 DOI 的期刊与筛选预期全部匹配，真实 Crossref/OpenAlex 重复 DOI 合并与 Semantic Scholar DOI 核对成功。匿名 Semantic Scholar 另有一次 HTTP 429，失败路径经实测。Python 3.14.10 通过 20 项自动化测试。

## READY

- 等待实际三个月回溯接续完成，验证本地同周补跑与最终站点，再保存可发布的本地数据状态和验收记录。

## BLOCKED

- 公开创建 GitHub 仓库、启用 Pages、首次正式部署、托管端自动触发和可访问性验证需要用户授权。

## 恢复

在项目根目录运行 `python -u -m energy_lit --state .work/live-state.json sync` 可接续本次验收。检查 `.work/live-state.bootstrap.json` 的 `next` 和当前运行进程；只有确认无同步进程后才处理残留锁。运行与恢复见 docs/operations.md。
