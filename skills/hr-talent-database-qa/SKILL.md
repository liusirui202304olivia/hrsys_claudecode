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

## 常用查询映射

- 岗位数量分布：`group_by=["position_name"]`
- 状态分布：`group_by=["status"]`
- 来源分布：`group_by=["source_name"]`
- 总量：`metrics=["count"]`
- 按岗位过滤：`filters={"position_query":"数据库岗位名或岗位关键词"}`
- 按状态过滤：`filters={"status":["SCREEN_PROCESS"]}`

## 输出要求

回答应包含：

- 查询口径
- 数据范围
- 结果表或列表
- 必要的限制说明，例如“只基于当前 MCP 返回的安全数据”

不要过度推理，不要把事实问答变成候选人推荐。
