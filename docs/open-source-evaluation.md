# Phase 0 开源评估

| 候选项目 | 许可 | 实测能力 | 主要不足与改造范围 |
| --- | --- | --- | --- |
| [Paper Digest](https://github.com/X-PG13/paper-digest/tree/8ed7900a68b4436cded7e35c6986da4b90ea2758) | MIT | Python 3.13 隔离环境，运行时零第三方依赖。关闭分析，分别用真实 Crossref 和 OpenAlex 检索，首次各命中 10 条、同窗重跑各新增 0 条。生成 JSON、状态文件、静态归档和 RSS。 | 源适配器不按目标期刊 ISSN 严格分页，数据结构缺失许可和可审计的期刊标识。归档默认会带上摘要，且包含本项目范围外的反馈、翻译和投递。整仓改造面大。 |
| [PaperRadar](https://github.com/zcz718/paperradar/tree/0a7a5749c6ba5db4419f5d86f48215b7225bd84a) | MIT | Python 3.13 隔离环境，原有 153 测试中 152 通过。Crossref 无 AI 实查 10 条带 DOI 记录，原有原子写入函数可保存并完整读回。 | Windows 的 PDF 测试使用带冒号的文件名，1 项失败。Crossref 仅一页，丢弃 ISSN，持续故障会返回空数组。OpenAlex 支持依赖 key，项目围绕 Skill、笔记和 Zotero，无 Pages 或 RSS 输出。全套依赖包含 PDF、浏览器与 Zotero 组件。 |
| [auto-paper-collecter](https://github.com/OvOhao/auto-paper-collecter/tree/54209b920ac4f2a551a7a5cf798e8cd681d374eb) | MIT | 源码审查。 | Python FastAPI、APScheduler、SQLite 和 Docker 服务。Crossref、Semantic Scholar 和入站 RSS 可用作设计参照，配置支持禁用 AI。缺少 OpenAlex、目标 ISSN 策略、静态 Pages 发布和测试工作流。改造需去除服务层与持续调度。 |
| [SciArgus](https://github.com/GMoncrieff/SciArgus/tree/6fdaf1d0f6442f84ab48e530ec7a167053cbb295) | 未发现明确许可 | 源码审查。 | Python requests、Jinja2 和 google-genai，Actions 定时邮件架构。以 OpenAlex 查询和期刊配置为主，缺少目标三源交叉校验、静态站点与 RSS；工作流涉及摘要与邮件密钥。无测试目录，源码不复制。 |

选择 **B**。从 Paper Digest 复用经过验证的无依赖重试实现和 OpenAlex 摘要解码，保留 MIT 版权及许可。论文模型、跨源期刊匹配、持久化、筛选和网站围绕 V1.0 实现，避免将上游的分析、翻译、投递和反馈功能带入。

四仓均按固定提交审查。两项真实检索均只访问元数据。Paper Digest 在补充 Windows IANA 时区数据后，原有 689 项测试中 687 项通过，剩余两项为 Windows 文档路径分隔符断言。PaperRadar 的失败项已在表中注明。
