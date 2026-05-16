---
name: hr-recruitment-report
description: Use when the user asks for a recruiting report, candidate pool report, weekly or monthly HR recruiting summary, or structured Markdown report.
---

# Recruitment Report Skill 招聘报告生成

## 适用场景

当用户要求生成候选池分析报告、岗位招聘报告、周报、月报或结构化 Markdown 报告时使用本 Skill。

本 Skill 负责报告组织和业务表达。后端 MCP/API 不生成报告，只提供安全数据和事实统计。

## 工作流

1. 确认报告主题、岗位、时间范围和输出粒度。
2. 如果报告涉及六类岗位之一，读取对应 Markdown 标准：`standard_markdown/xiaoman.md` 或 `standard_markdown/yihai.md`。
3. 调用 `query_talent_pool_facts` 获取统计事实。
4. 必要时调用 `search_candidate_safe_profiles` 或 `get_candidate_safe_detail_batch` 获取安全样本证据。
5. 由 Agent 生成报告内容，区分数据事实和业务判断。
6. 报告不得包含联系方式字段。
7. 如果报告中包含推荐候选人，推荐判断必须遵循 Candidate Screening Skill 的标准。

## 报告建议结构

- 标题
- 报告范围
- 标准来源
- 数据口径
- 候选池概览
- 岗位/状态/来源分布
- 样本候选人证据
- 推荐或关注候选人，如果适用
- 风险点
- 下一步建议

## 注意事项

- 不要调用不存在的后端报告生成工具。
- 不要把后端事实查询结果原样堆砌成报告；需要由 Agent 组织结构和业务表达。
- 不要为没有 Markdown 标准的岗位生成推荐结论，可以生成事实性数据报告并说明标准缺失。
