---
name: hr-candidate-screening
safe_sql_guidance: query_hr_safe_sql, describe_hr_safe_schema, 安全 SQL, 业务判断
description: Use when the user asks to screen, rank, recommend, or explain candidates for the supported HR recruiting positions in this project.
---

## 安全 SQL 宽召回补充

当 `search_candidate_safe_profiles` 的固定过滤不足以表达用户的筛选意图时，可以调用 `describe_hr_safe_schema` 查看安全字段，再用 `query_hr_safe_sql` 从 `v_candidate_agent_safe` 做宽召回。安全 SQL 只负责取数；业务判断、岗位标准匹配、老板偏好、推荐等级、风险点和面试验证建议仍由本 Skill 完成。

使用安全 SQL 时必须遵守：

- 不查原始表，不查联系方式字段。
- 不把候选人的来源岗位当成目标岗位；目标岗位来自用户意图和 Markdown 标准。
- 推荐输出仍必须包含 `candidate_id`、候选人姓名 `name`、目标岗位、来源岗位、是否跨岗位推荐、匹配证据、风险点和面试验证建议。
- 对“准备入职”相关问题，默认按 `proposed_join_date`，并排除 `REJECTED`、`HIRED`。

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
3. 按“候选人召回与推荐池策略”调用 `search_candidate_safe_profiles` 召回全库安全画像。不要默认用目标岗位名做 position_query 窄筛。
4. 如果候选人证据不足，调用 `get_candidate_safe_detail_batch` 补充安全详情。
5. 对每个候选人逐条对照 Markdown 标准，分为优先推荐、补充考虑、暂不推荐。
6. 推荐理由必须引用候选人安全画像中的事实证据，不要泛泛而谈。
7. 风险点必须具体，例如项目主导性不足、方向相关性不足、稳定性待确认、关键技能深度不足。
8. 给出面试验证建议，但不要生成联系方式。
9. 用户要求保存时，调用 `save_screening_result`。

## 候选人召回与推荐池策略

1. 默认先调用 `search_candidate_safe_profiles`，从全库安全画像的 `active` 池做宽召回。根据 Markdown 岗位标准提取核心技能、项目经历、领域关键词，`filters` 使用：

   ```json
   {
     "candidate_pool": "active",
     "skills_any": ["<标准中的核心技能1>", "<标准中的核心技能2>"],
     "experience_keywords_any": ["<标准中的项目/领域关键词1>", "<标准中的项目/领域关键词2>"]
   }
   ```

   只从仍在招聘流程中的候选人里做第一轮推荐。`skills_any` 和 `experience_keywords_any` 是宽召回条件，命中任一关键词即可进入候选池；精筛和推荐判断由本 Skill 对照 Markdown 标准完成。

   搜索和详情读取时必须请求并保留 `candidate_id` 和 `name`。推荐输出必须显示候选人姓名，不要只显示 ID。

2. `candidate.position_id`、`candidate.position_name`、`position_jd` 是候选人的来源岗位或当前归属岗位，不是本次推荐的目标岗位。来源岗位不一致不能直接排除候选人。

3. 必须主动考虑关联岗位和近似岗位候选人：如果候选人的技术栈、项目经历、行业经验、岗位 JD 与目标岗位标准强相关，即使原 `position_id` 属于其他岗位，也可以作为跨岗位推荐候选人。

4. `position_query` 只能作为来源岗位/关联岗位辅助召回条件，不能作为默认唯一过滤条件。只有在需要补充某类关联岗位来源候选人时才使用，例如：

   ```json
   {
     "candidate_pool": "active",
     "position_query": "<关联岗位或近似岗位关键词>",
     "skills_any": ["<核心技能>"]
   }
   ```

5. 如果 `active` 池候选人不足，或用户明确要求“扩大范围/捞历史候选人”，再调用：

   ```json
   {
     "candidate_pool": "old_rejected",
     "rejected_before_days": 180,
     "skills_any": ["<标准中的核心技能1>", "<标准中的核心技能2>"],
     "experience_keywords_any": ["<标准中的项目/领域关键词1>", "<标准中的项目/领域关键词2>"]
   }
   ```

   只考虑 `status=REJECTED` 且 `update_time` 距今超过 180 天的候选人。

6. 不要推荐 `recent_rejected` 候选人。近期被拒候选人只能出现在“不推荐/暂不推荐”或分析说明中。

7. `hired` / `HIRED` 候选人默认不进入推荐池，只能用于人才画像、历史供给或报告分析。

8. `old_rejected` 候选人只有高度匹配 Markdown 岗位标准时才可推荐，并必须标注为“历史拒绝补充考虑”，不能和 `active` 候选人混在同一优先级里。

9. `old_rejected` 推荐理由必须说明：

   - 候选人虽历史被拒，但哪些证据强匹配当前岗位标准；
   - `update_time` 是状态更新时间，在 `REJECTED` 状态下视作被拒时间；
   - `reject_stage` 或拒绝原因缺失时，必须作为风险点。

10. 跨岗位推荐必须说明：

   - 目标岗位是什么；
   - 候选人来源岗位是什么；
   - 为什么来源岗位不同但仍匹配目标岗位标准；
   - 跨岗位风险是什么；
   - 面试中需要验证哪些目标岗位能力。

11. 推荐输出必须分层：

   - 优先推荐：`active` 池强匹配候选人；
   - 补充考虑：`old_rejected` 且超过 180 天、强匹配候选人；
   - 暂不推荐：`recent_rejected`、证据不足、岗位标准不匹配、已入职。

## 老板偏好

老板偏好用于推荐排序、推荐理由和风险说明，不是后端硬过滤条件；不能因为某个偏好缺失就直接排除候选人，除非岗位 Markdown 标准本身也不匹配。

通用偏好：

1. 学校背景好优先。国内 top 985、211、强势专业院校和海外优秀学校是加分项；如果学校信息缺失，要标为待确认。
2. 偏好高潜年轻人。年轻、成长速度快、项目复杂度提升明显、技术栈贴近目标岗位的候选人可以提高优先级。
3. 跳槽不能频繁。履历中短期多段经历、频繁换工作、每段时间过短，需要作为风险点说明；如果履历时间线不完整，要提示需要面试确认稳定性。

个别岗位偏好：

1. 如果是招研发岗位 leader，偏好 35岁 左右、带过团队、有明确 sig owner 角色或能对关键模块/项目结果负责的人。
2. 研发岗位会偏好大厂背景履历。大厂背景、复杂工程体系经验、规模化项目经历是加分项，但仍必须回到 Markdown 岗位标准和候选人安全画像证据，不要只因为有大厂经历就推荐。

使用这些偏好时必须说明证据来源，例如学校、履历、项目经历、团队管理经历、sig owner 角色、大厂背景；没有证据时只能写“待确认”，不能编造。

## 输出要求

推荐输出应包含：

- 岗位和标准来源
- 查询范围和召回数量
- 推荐候选人列表
- 每人的 `candidate_id`
- 每人的候选人姓名 `name`
- 目标岗位
- 候选人来源岗位
- 是否跨岗位推荐
- 匹配证据
- 推荐理由
- 风险点
- 跨岗位风险
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
