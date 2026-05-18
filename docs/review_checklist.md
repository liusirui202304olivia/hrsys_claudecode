# HR MCP/API P0 Review Checklist

## 架构边界

- [ ] `hr_mcp/http/app.py` 只处理 HTTP、JSON、header、JSON-RPC 调用，不直接访问数据源。
- [ ] `hr_mcp/mcp/jsonrpc.py` 只处理 MCP over HTTP JSON-RPC 编解码。
- [ ] `hr_mcp/services/tool_router.py` 只根据工具名分发安全数据能力，不直接访问数据源。
- [ ] Identity、权限、工具注册、工具路由、候选人安全画像、召回、事实查询、结果存储、审计分别在独立文件中。
- [ ] 后端不实现岗位标准读取、候选人推荐、自然语言问答、招聘分析或报告生成。
- [ ] Claude Code Skill 负责读取 `standard_markdown`、执行筛选推荐、问答、分析和报告。
- [ ] Skill 按业务任务拆为总入口、候选人筛选推荐、人才库业务问答、招聘数据分析、招聘汇报/PPT 页生成五个一级 Skill。
- [ ] 不存在一个超大 HR 业务 Skill，也不存在按工具动作拆分的“读取标准/读取候选人/统计数量/保存结果”业务 Skill。
- [ ] P0 不包含飞书机器人、Web Chat、考勤、绩效、薪酬业务逻辑。

## 字段安全

- [ ] 所有候选人输出经过 `candidate_safe_view_service.py`。
- [ ] 字段白名单集中在 `security/field_policy.py`。
- [ ] `candidate_id` 是非敏感默认可见字段，搜索结果必须返回可用于 `save_screening_result` 复用的 ID。
- [ ] `name`、`gender`、`proposed_join_date` 原文开放，不做掩码。
- [ ] `mobile`、`email`、`phone`、`username` 只允许高权限角色和访问理由。
- [ ] 未列入默认可见或高权限可见的字段全部拒绝。
- [ ] 高权限字段访问写入审计日志，包含 `X-Access-Reason`。

## 数据访问

- [ ] `mysql_repository.py` 的常规路径只接受受控 filter；开放问题只能通过 `query_hr_safe_sql` 的安全 SQL 沙箱查询安全 view。
- [ ] `search_candidate_safe_profiles` 只限制单次 `page_size`，返回 `total_count`、`has_more`、`next_cursor`，不限制参与查询的候选人总量。
- [ ] `query_talent_pool_facts` 使用 repository 的 `COUNT(*)` / `GROUP BY` 聚合，不通过拉取固定条数候选人做 Python 统计。
- [ ] `get_candidate_safe_detail_batch` 超过单次 50 个 ID 时拒绝请求，不静默截断。
- [ ] `HR_DATA_BACKEND` 必须显式配置；真实内网联调使用 `mysql`，`dump` 仅用于显式本地测试。
- [ ] SQL dump 验证路径可解析核心表。
- [ ] 安全视图 SQL 不把联系方式放入默认视图。
- [ ] 客户端配置不包含数据库账号、密码或连接串。

## HTTP / Auth

- [ ] `GET /healthz` 返回存活状态。
- [ ] `GET /readyz` 返回数据源、审计存储状态，不依赖 `standard_markdown`。
- [ ] `POST /mcp` 支持 `tools/list` 和 `tools/call`。
- [ ] `GET /mcp/tools` 仅管理员或调试角色可用。
- [ ] `/mcp` 使用 `Authorization: Bearer <token>` 鉴权。
- [ ] 客户端伪造 `X-User-Role`、`X-User-Id`、`X-Department-Id` 不会覆盖服务端 token 身份。
- [ ] IP 白名单、限流和请求体大小限制生效。

## MCP Tools

- [ ] MCP `tools/list` 返回 6 个安全数据工具。
- [ ] `search_candidate_safe_profiles` 返回安全候选人画像。
- [ ] `get_candidate_safe_detail_batch` 批量读取安全详情且限制批量大小。
- [ ] `query_talent_pool_facts` 只返回事实统计和聚合分布。
- [ ] `query_hr_safe_sql` 只允许单条 `SELECT`，只查询安全 view，强制 limit，并审计成功和失败。
- [ ] `describe_hr_safe_schema` 返回安全 SQL 可查询字段，普通角色看不到联系方式字段。
- [ ] `save_screening_result` 只保存 Agent 生成的 `task_id`、`standard_ref`、`candidate_id`、`recommend_reason`、`risk_points`。
- [ ] 后端不暴露 `get_screening_policy`、`analyze_talent_pool`、`generate_recruitment_report`。

## 测试

- [ ] `python -m pytest tests -q` 通过。
- [ ] 默认角色请求高权限字段被拒绝。
- [ ] `HR_ADMIN` 携带 `X-Access-Reason` 时可访问高权限字段。
- [ ] 本地 smoke 覆盖候选人召回、人才库事实查询和推荐结果保存。
- [ ] `skills/hr-talent-intelligence/SKILL.md` 能路由到四个业务 Skill。
- [ ] `skills/hr-candidate-screening/SKILL.md` 覆盖六类岗位标准映射和推荐结果保存格式。
- [ ] `skills/hr-talent-database-qa/SKILL.md` 只做事实问答，不生成推荐结论。
- [ ] `skills/hr-talent-analysis/SKILL.md` 做数据分析并区分事实和 Agent 推断。
- [ ] `skills/hr-recruitment-report/SKILL.md` 生成 HR 汇报/PPT 型报告页，不调用后端报告生成工具。
- [ ] 招聘报告 Skill 覆盖招聘漏斗、转化率、流失原因、关键指标卡、图表建议和行动建议。
