# 运行与恢复

## GitHub Pages

获得公开发布授权后，将仓库配置为公开仓库，并在 Settings → Pages → Source 选择 GitHub Actions。工作流按默认分支运行。仓库规则必须允许 Actions 机器人以快进方式写入同步提交。可以在 Actions → Update literature and deploy Pages 手动运行同一工作流。

调度使用 GitHub Actions 的 IANA 时区字段，`0 9 * * 1` 配合 `Asia/Shanghai` 表示北京时间周一 09:00（UTC 01:00）。GitHub 可能延迟调度。工作流按组串行，且默认分支发生并发更新时，普通推送会被拒绝。重跑从最新默认分支开始。 [GitHub 调度说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

可选配置为 GitHub Actions secrets 中的 `OPENALEX_API_KEY`、`S2_API_KEY` 和 `CROSSREF_EMAIL`。只使用免费接口。OpenAlex 匿名入口走普通页码，有免费 key 时可以走游标。Crossref 匿名接口的共享限流、Semantic Scholar 429 和数据源索引时差可能降低覆盖率。更新时保留失败来源与历史批次的状态。

## 写入与发布保护

本地同步用独占锁和原子替换保护状态文件。断电后发现残留的 `data/state.lock` 时，先确认没有同步进程，再移除该锁。引导回溯期间每成功一批保存单独检查点。获取失败时，只持久化已验证的检查点，若已有可验证的线上数据，则构建保留历史的状态提示。同步命令在 30 分钟时主动结束，为持久化检查点留出时间。手动取消整个 GitHub 作业时，本次尚未提交的检查点随临时运行器消失。无可用初始数据时，部署跳过。验证或异常变动检查失败时，工作流停在提交和部署之前。

## 恢复演练和回滚

每次成功同步存储由 `git archive --format=zip --output=literature-snapshot.zip HEAD data config` 生成的快照，Actions 保留 90 天。快照包含数据、期刊、规则、审核和许可记录。Git 提交同时提供长期恢复路径。

1. 将已知正常快照解压到独立临时目录。用同一提交的代码，执行 `python -m energy_lit --state <快照目录>/data/state.json validate`。当配置有差异时，先在独立 Git 检出中使用同一份快照配置进行验证。
2. 对照 DOI 数量、周报范围和人工审核记录。若只回滚数据，在独立分支执行 `git restore --source=<已验证提交> -- data/state.json`，保留现行审核与许可文件，再验证并提交。
3. 审查变更后合并。若有权立即恢复线上版本，从已验证提交构建 Pages 工件，再完成部署验证。重新同步会以已恢复版本的最后成功时间补查。公开操作需要已授予的仓库和部署权限。

依赖锁定在 Python 版本和 Actions 的提交 SHA。Dependabot 仅提交更新建议，CI 在合并前运行测试、数据校验和静态构建。
