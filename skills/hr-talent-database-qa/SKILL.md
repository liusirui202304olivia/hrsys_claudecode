---
name: hr-talent-database-qa
description: Use when the user asks factual questions about the HR talent database, counts, distributions, status, sources, or safe candidate details.
---

# Talent Database QA Skill 人才库业务问答

## 适用场景

当用户提出人才库事实问题时使用本 Skill，例如：

- “库里各岗位候选人数量分布怎么样？”
- “某岗位有多少人在流程中？”
- “某来源的候选人多不多？”
- “某候选人的安全画像里有什么信息？”

本 Skill 的目标是准确回答事实，不做筛选推荐结论，不生成报告。

## 工作流

1. 解析用户问题，确认是统计类、分布类还是明细类。
2. 统计和分布类优先调用 `query_talent_pool_facts`。
3. 候选人明细类调用 `search_candidate_safe_profiles` 或 `get_candidate_safe_detail_batch`。
4. 输出查询范围、筛选条件和事实结果。
5. 如需要解释，明确区分数据事实和轻量说明。
6. 不要基于问答直接生成“推荐/不推荐”结论。
7. 不输出联系方式字段。

事实问答不默认套推荐池策略。用户问“库里多少人”“分布怎么样”时，按用户问题原样统计，并明确说明状态口径；只有用户明确限定“流程中”“历史拒绝”“近期拒绝”“已入职”时，才使用 `candidate_pool` 过滤。

## 常用查询映射

- 岗位数量分布：`group_by=["position_name"]`
- 状态分布：`group_by=["status"]`
- 来源分布：`group_by=["source_name"]`
- 总量：`metrics=["count"]`
- 按岗位过滤：`filters={"position_query":"数据库岗位名或岗位关键词"}`
- 按状态过滤：`filters={"status":["SCREEN_PROCESS"]}`
- 流程中候选人：`filters={"candidate_pool":"active"}`
- 历史拒绝候选人：`filters={"candidate_pool":"old_rejected","rejected_before_days":180}`
- 近期拒绝候选人：`filters={"candidate_pool":"recent_rejected","rejected_before_days":180}`
- 已入职候选人：`filters={"candidate_pool":"hired"}`

## 输出要求

回答应包含：

- 查询口径
- 数据范围
- 结果表或列表
- 必要的限制说明，例如“只基于当前 MCP 返回的安全数据”

不要过度推理，不要把事实问答变成候选人推荐。

## 开放式安全 SQL 能力

当用户的问题不是现有枚举工具能稳定覆盖的高频问法时，可以先调用 `describe_hr_safe_schema` 查看可查询的安全 view 和字段，再调用 `query_hr_safe_sql` 写只读安全 SQL。看什么数据由 Agent 判断，业务判断由 Skill 指导，安全边界由 MCP/API 后端控制。

安全 SQL 只能查后端允许的安全 view，不能查原始表，不能请求联系方式字段。回答时必须说明查询口径、时间范围和状态口径。

常见高频问法映射：

- “看看某某的信息”：优先用 `search_candidate_safe_profiles` 的 `name_query`；如果需要组合更多条件，再用 `query_hr_safe_sql`。
- “最近一个月有哪些人准备入职”：按 `proposed_join_date` 查询，默认排除 `REJECTED`、`HIRED`，并说明这是拟入职时间口径。
- “最近入职了哪些人”：只有用户明确问“已入职/入职了”时，才查 `HIRED`。
- “某部门/某岗位/某来源最近变化”：可以用 `query_talent_pool_facts`，也可以用安全 SQL 做趋势和分组。

示例安全 SQL：

```sql
SELECT candidate_id, name, status, proposed_join_date, position_name
FROM v_candidate_agent_safe
WHERE proposed_join_date BETWEEN '2026-05-01' AND '2026-05-31'
  AND status NOT IN ('REJECTED', 'HIRED')
ORDER BY proposed_join_date ASC
LIMIT 100
```
