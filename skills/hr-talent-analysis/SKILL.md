---
name: hr-talent-analysis
description: Use when the user asks for recruiting data analysis, candidate pool structure, supply gaps, process bottlenecks, or source quality insights.
---

# Talent Analysis Skill 招聘数据分析

## 适用场景

当用户要求分析招聘数据、候选池结构、供给缺口、流程积压、来源质量或岗位供给情况时使用本 Skill。

本 Skill 负责分析推理。后端 MCP/API 只返回事实数据和安全候选人画像。

## 工作流

1. 明确分析对象和范围：岗位、部门、状态、来源、时间或候选池。
2. 调用 `query_talent_pool_facts` 获取 count、岗位分布、状态分布、来源分布等事实。
3. 必要时调用 `search_candidate_safe_profiles` 召回少量安全样本，作为分析证据。
4. 由 Agent 基于事实数据完成结构分析、风险判断和改进建议。
5. 输出时明确标注数据事实、Agent 推断、风险或不确定性、建议动作。
6. 不生成完整招聘报告；如果用户要求报告，切换到 Recruitment Report Skill。
7. 不输出联系方式字段。

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
