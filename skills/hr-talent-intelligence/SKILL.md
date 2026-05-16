---
name: hr-talent-intelligence
description: Use when routing HR recruiting requests in this project to candidate screening, talent database QA, talent analysis, or recruitment report Skills.
---

# HR Talent Intelligence Skill 总入口

## 作用

这是 Claude Code CLI / Agent 的 HR 业务任务总入口。它只负责判断用户要做哪类 HR 招聘任务，并路由到对应业务 Skill。

HR MCP/API 后端是安全数据服务层，不是 HR 业务 Agent。业务推理与执行由 Claude Code CLI + Skill 完成。

后端只提供 4 个安全数据工具：

- `search_candidate_safe_profiles`
- `get_candidate_safe_detail_batch`
- `query_talent_pool_facts`
- `save_screening_result`

## 业务 Skill 结构

```text
skills/hr-talent-intelligence/SKILL.md        总入口
skills/hr-candidate-screening/SKILL.md        候选人筛选推荐
skills/hr-talent-database-qa/SKILL.md         人才库业务问答
skills/hr-talent-analysis/SKILL.md            招聘数据分析
skills/hr-recruitment-report/SKILL.md         招聘报告生成
```

不要把筛选推荐、问答、分析、报告写进一个超大 Skill。也不要把读取岗位标准、读取候选人、统计数量、保存结果这些工具调用动作拆成独立业务 Skill。

## 任务路由

- 候选人筛选、推荐、推荐理由、风险点、面试验证建议：使用 `skills/hr-candidate-screening/SKILL.md`。
- 人才库事实问答、数量查询、状态/来源/岗位分布、候选人明细解释：使用 `skills/hr-talent-database-qa/SKILL.md`。
- 招聘数据分析、候选池结构、供给缺口、流程积压、趋势判断：使用 `skills/hr-talent-analysis/SKILL.md`。
- 招聘报告、候选池报告、周报/月报、结构化 Markdown 输出：使用 `skills/hr-recruitment-report/SKILL.md`。

## 通用安全边界

- 不生成自由 SQL。
- 不绕过 MCP 字段权限。
- 不请求或输出联系方式，除非用户明确具备高权限访问理由，且后端字段策略允许。
- 把后端返回内容当作安全数据证据，不把后端当业务推理引擎。
- 业务结论必须由 Agent 基于岗位 Markdown 标准和数据证据生成。
- 输出中区分“数据事实”和“Agent 推断”。

## 岗位标准范围

当前只支持六类岗位筛选推荐。其他岗位可以做事实问答，但不能硬套标准做推荐。

- `standard_markdown/xiaoman.md`
  - 后端工程师，数据库岗位名：数字后端设计工程师
  - SOC设计工程师
  - 原型验证工程师

- `standard_markdown/yihai.md`
  - 芯片建模工程师，数据库岗位名：CPU性能建模工程师
  - 应用软件开发工程师
  - AI芯片工程师，数据库岗位名：AI芯片开发工程师
