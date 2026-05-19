---
name: hr-talent-intelligence
safe_sql_guidance: query_hr_safe_sql, describe_hr_safe_schema, 安全 SQL
description: 当需要把 HR 招聘问题路由到候选人筛选、人才库问答、招聘数据分析或招聘汇报 Skill 时使用。
---

# HR 招聘智能总入口 Skill

## 作用

这是 Claude Code CLI / Agent 的 HR 业务任务总入口。它只负责判断用户要做哪类 HR 招聘任务，并路由到对应业务 Skill。

HR MCP/API 后端是安全数据服务层，不是 HR 业务 Agent。业务推理与执行由 Claude Code CLI + Skill 完成。

后端只提供 6 个安全数据工具：

- `search_candidate_safe_profiles`
- `get_candidate_safe_detail_batch`
- `query_talent_pool_facts`
- `query_hr_safe_sql`
- `describe_hr_safe_schema`
- `save_screening_result`

## 当前能力总览

Agent 当前可处理四类 HR 招聘任务：候选人筛选推荐、人才库事实问答、招聘数据分析、招聘汇报/PPT 页生成。所有任务都必须先选择对应业务 Skill，再通过 MCP/API 的安全工具取数。

6 个 MCP 工具的用途：

- `search_candidate_safe_profiles`：按安全条件召回候选人画像，用于筛选、样本分析和事实问答。
- `get_candidate_safe_detail_batch`：批量读取候选人安全详情，用于补充推荐或分析证据。
- `query_talent_pool_facts`：获取固定聚合事实，例如总量、岗位分布、状态分布、来源分布。
- `describe_hr_safe_schema`：查看 `query_hr_safe_sql` 可查询的安全 view、字段、字段含义和可聚合字段。
- `query_hr_safe_sql`：执行单条只读安全 SQL，用于开放式事实查询、组合筛选和聚合分析。
- `save_screening_result`：在用户明确要求保存时写入筛选推荐结果。

当前 `query_hr_safe_sql` 可查询的安全 view：

- `v_candidate_agent_safe`：候选人基础安全画像，包含状态、岗位、来源、经历、技能、拟入职时间等默认可见字段，不包含联系方式。
- `v_candidate_agent_privileged`：高权限候选人视图，只能在 `HR_ADMIN` 且有访问理由时用于联系方式读取；普通 Agent 不应主动使用。
- `v_candidate_interview_safe`：面试记录，包含候选人/岗位上下文、面试名称、面试类型、面试时间和面试状态。
- `v_candidate_interview_evaluate_safe`：面试评价，包含评价文本、`evaluate_data`、`question_data`、`evaluation_result` 和候选人/岗位/面试官上下文。
- `v_candidate_interview_question_safe`：面试评价 JSON 拆出的可聚合明细，包含 `score`、题目、回答、反馈、维度和面试官上下文。
- `v_candidate_screen_evaluate_safe`：初筛评价，包含初筛反馈、`screen_result` 和候选人/岗位/筛选人上下文。

开放式问题默认先调用 `describe_hr_safe_schema`，再由 Agent 判断查询候选人画像、面试记录、评价文本、评分明细、初筛评价还是聚合统计。禁止查询原表和 schema 外字段，禁止绕过字段白名单、行级范围和审计。

## 业务 Skill 结构

```text
skills/hr-talent-intelligence/SKILL.md        总入口
skills/hr-candidate-screening/SKILL.md        候选人筛选推荐
skills/hr-talent-database-qa/SKILL.md         人才库业务问答
skills/hr-talent-analysis/SKILL.md            招聘数据分析
skills/hr-recruitment-report/SKILL.md         招聘汇报/PPT 页生成
```

不要把筛选推荐、问答、分析、报告写进一个超大 Skill。也不要把读取岗位标准、读取候选人、统计数量、保存结果这些工具调用动作拆成独立业务 Skill。

## 任务路由

- 候选人筛选、推荐、推荐理由、风险点、面试验证建议：使用 `skills/hr-candidate-screening/SKILL.md`。
- 人才库事实问答、数量查询、状态/来源/岗位分布、候选人明细解释：使用 `skills/hr-talent-database-qa/SKILL.md`。
- 招聘数据分析、候选池结构、供给缺口、流程积压、趋势判断：使用 `skills/hr-talent-analysis/SKILL.md`。
- 招聘报告、候选池报告、招聘漏斗分析、周报/月报、PPT 汇报页输出：使用 `skills/hr-recruitment-report/SKILL.md`。

## 通用安全边界

- 不生成越过 `query_hr_safe_sql` 安全沙箱的原始库 SQL。
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
