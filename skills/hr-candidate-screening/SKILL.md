---
name: hr-candidate-screening
description: Use when the user asks to screen, rank, recommend, or explain candidates for the supported HR recruiting positions in this project.
---

# Candidate Screening Skill 候选人筛选推荐

## 适用场景

当用户要求“筛一筛”“推荐候选人”“哪些人适合某岗位”“给推荐理由/风险点/面试验证建议”时使用本 Skill。

本 Skill 负责业务判断。HR MCP/API 后端只提供安全候选人数据、事实查询和保存结果能力。

## 支持岗位与标准

只对以下六类岗位做筛选推荐：

### `standard_markdown/xiaoman.md`

- 后端工程师
  - 数据库岗位名：数字后端设计工程师
  - 别名：后端工程师、数字后端、数字后端设计、后端设计工程师

- SOC设计工程师
  - 别名：SOC设计、SoC设计、SOC设计工程师

- 原型验证工程师
  - 别名：原型验证、FPGA原型验证、验证工程师

### `standard_markdown/yihai.md`

- 芯片建模工程师
  - 数据库岗位名：CPU性能建模工程师
  - 别名：芯片建模、CPU性能建模、性能建模、建模工程师

- 应用软件开发工程师
  - 别名：应用软件、应用开发、软件开发、C++开发、系统软件

- AI芯片工程师
  - 数据库岗位名：AI芯片开发工程师
  - 别名：AI芯片、AI芯片开发、AI芯片工程师

六类之外的岗位：不要推荐，说明当前缺少对应 Markdown 标准，需要部门负责人补充。

## 工作流

1. 识别用户目标岗位，映射到上述标准文件和数据库岗位名。
2. 直接读取对应 Markdown 标准全文。
3. 调用 `search_candidate_safe_profiles` 召回安全候选人画像，优先用数据库岗位名做 `position_query`。
4. 如果候选人证据不足，调用 `get_candidate_safe_detail_batch` 补充安全详情。
5. 对每个候选人逐条对照 Markdown 标准，分为推荐、待确认、不推荐。
6. 推荐理由必须引用候选人安全画像中的事实证据，不要泛泛而谈。
7. 风险点必须具体，例如项目主导性不足、方向相关性不足、稳定性待确认、关键技能深度不足。
8. 给出面试验证建议，但不要生成联系方式。
9. 用户要求保存时，调用 `save_screening_result`。

## 输出要求

推荐输出应包含：

- 岗位和标准来源
- 查询范围和召回数量
- 推荐候选人列表
- 每人的 `candidate_id`
- 推荐理由
- 风险点
- 面试验证建议
- 不推荐或待确认的简要原因

不要只做字段拼接；必须基于岗位 Markdown 标准和候选人安全画像做判断。

## 保存结果格式

调用 `save_screening_result` 时只保存：

```json
{
  "task_id": "screen-YYYYMMDD-001",
  "standard_ref": "standard_markdown/yihai.md#CPU性能建模工程师",
  "recommended_candidates": [
    {
      "candidate_id": 123,
      "recommend_reason": "候选人的项目经历和技能证据如何匹配 Markdown 标准。",
      "risk_points": ["需要面试确认的风险点"]
    }
  ]
}
```

后端应返回 `candidate_id`。如果搜索或详情结果缺少 `candidate_id`，停止保存推荐结果并报告数据契约问题；不要使用其他字段替代，也不要编造 ID。
