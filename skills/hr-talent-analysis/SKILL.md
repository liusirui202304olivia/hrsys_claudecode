---
name: hr-talent-analysis
safe_sql_guidance: query_hr_safe_sql, describe_hr_safe_schema, 安全 SQL, 业务判断
description: 当用户要求招聘数据分析、候选池结构、供给缺口、流程瓶颈或来源质量洞察时使用。
---

# 招聘数据分析 Skill

## 适用场景

当用户要求分析招聘数据、候选池结构、供给缺口、流程积压、来源质量或岗位供给情况时使用本 Skill。

本 Skill 负责分析推理。后端 MCP/API 只返回事实数据和安全候选人画像。

## 当前可用数据能力

- 固定聚合：优先使用 `query_talent_pool_facts` 获取总量、岗位分布、状态分布、来源分布等常见事实。
- 安全样本：需要解释结构或风险时，用 `search_candidate_safe_profiles` 获取少量安全候选人样本；必要时用 `get_candidate_safe_detail_batch` 补充安全详情。
- 灵活聚合：当用户从时间、部门、岗位、来源、趋势、候选人结构等多个维度组合提问时，先调用 `describe_hr_safe_schema`，再用 `query_hr_safe_sql` 查询安全 view。安全 SQL 只返回事实数据；趋势解释、风险识别和行动建议仍由本 Skill 完成。
- 候选人基础分析：`v_candidate_agent_safe` 可用于状态、岗位、来源、学历、学校、专业、工作年限、拟入职时间、创建时间和更新时间等维度。
- 面试过程分析：`v_candidate_interview_safe` 可按 `interview_status`、`interview_type`、`position_name`、`interview_time` 做面试状态、类型、岗位和时间分析。
- 面试评价分析：`v_candidate_interview_evaluate_safe` 可按候选人、岗位、面试官和 `evaluation_result` 分析评价结果和反馈文本。
- 评分/题目维度分析：`v_candidate_interview_question_safe` 可做 `AVG(score)`、评分分布、题目维度、面试官评分对比和问答明细分析。
- 初筛评价分析：`v_candidate_screen_evaluate_safe` 可按 `screen_result`、岗位、候选人和筛选人分析初筛结果与反馈。

涉及“准备入职”的分析默认使用 `proposed_join_date`，并排除 `REJECTED`、`HIRED`；涉及“最近变化”时要说明使用 `create_time` 还是 `update_time`。禁止查询原表：`hr_interview`、`hr_interview_evaluate`、`hr_screen_evaluate`，也禁止查询 `describe_hr_safe_schema` 未列出的字段。

## 工作流

1. 明确分析对象和范围：岗位、部门、状态、来源、时间或候选池。
2. 调用 `query_talent_pool_facts` 获取 count、岗位分布、状态分布、来源分布等事实。
3. 必要时调用 `search_candidate_safe_profiles` 召回少量安全样本，作为分析证据。
4. 由 Agent 基于事实数据完成结构分析、风险判断和改进建议。
5. 输出时明确标注数据事实、Agent 推断、风险或不确定性、建议动作。
6. 不生成完整招聘报告；如果用户要求报告，切换到招聘汇报生成 Skill。
7. 不输出联系方式字段。

候选池结构分析要拆分四类口径：

- `active`：仍在招聘流程中的主候选池。
- `old_rejected`：`status=REJECTED` 且 `update_time` 超过 180 天的历史拒绝补充池。
- `recent_rejected`：近期被拒候选人，主要用于说明不可推荐量、拒绝压力或流程问题。
- `hired`：已入职候选人，主要用于历史供给、成功画像和转化分析。

分析可以比较这四类池的人数、岗位分布和状态变化，但不要把 `recent_rejected` 或 `hired` 写成默认可推荐人群。

## 分析维度

可使用以下维度组织分析：

- 岗位供给：候选人数量、岗位分布、稀缺岗位。
- 流程状态：筛选中、已淘汰、面试中、拟入职等状态分布。
- 来源结构：来源分布和潜在来源风险。
- 候选人结构：学历、学校、专业、工作年限、技能栈，仅基于安全字段。
- 风险点：样本不足、状态积压、岗位供给不足、证据缺失。

## 输出要求

输出结构建议：

1. 分析范围
2. 数据事实
3. 关键发现
4. 风险点
5. 后续建议

不要把分析结果保存为推荐结果；只有筛选推荐任务才调用 `save_screening_result`。
