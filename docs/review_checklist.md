# HR MCP/API P0 Review Checklist

## 架构边界

- [ ] `hr_mcp/http/app.py` 只处理 HTTP、JSON、header、JSON-RPC 调用，不直接访问数据源。
- [ ] `hr_mcp/mcp/jsonrpc.py` 只处理 MCP over HTTP JSON-RPC 编解码。
- [ ] `hr_mcp/services/tool_router.py` 只根据工具名分发，不直接访问数据源。
- [ ] Identity、权限、工具注册、工具路由、岗位标准、候选人安全画像、召回、问答、分析、报告、结果存储、审计分别在独立文件中。
- [ ] P0 不包含飞书机器人、Web Chat、考勤、绩效、薪酬业务逻辑。

## 字段安全

- [ ] 所有候选人输出经过 `candidate_safe_view_service.py`。
- [ ] 字段白名单集中在 `security/field_policy.py`。
- [ ]
ame`、`gender`、`proposed_join_date` 原文开放，不做掩码。
- [ ] `mobile`、`email`、`phone`、`username` 只允许高权限角色和访问理由。
- [ ] 未列入默认可见或高权限可见的字段全部拒绝。
- [ ] 高权限字段访问写入审计日志，包含 `X-Access-Reason`。

## 数据访问

- [ ] `mysql_repository.py` 只接受受控 filter，不暴露自由 SQL。
- [ ] SQL dump 验证路径可解析核心表。
- [ ] 安全视图 SQL 不把联系方式放入默认视图。
- [ ] 客户端配置不包含数据库账号、密码或连接串。

## HTTP / Gateway

- [ ] `GET /healthz` 返回存活状态。
- [ ] `GET /readyz` 返回数据源、标准库、审计存储状态。
- [ ] `POST /mcp` 支持 `tools/list` 和 `tools/call`。
- [ ] `GET /mcp/tools` 仅管理员或调试角色可用。
- [ ] Gateway 注入 `X-Request-Id`、`X-Trace-Id`、`X-User-Id`、`X-User-Name`、`X-User-Role`、`X-Department-Id`、`X-Client-Id`、`X-Access-Reason`。
- [ ] 生产环境配置 `HR_GATEWAY_SHARED_SECRET`，并确认直连伪造 Gateway header 会被拒绝。

## 测试

- [ ] `python -m pytest tests -q` 通过。
- [ ] MCP `tools/list` 返回 7 个工具。
- [ ] 默认角色请求高权限字段被拒绝。
- [ ] `HR_ADMIN` 携带 `X-Access-Reason` 时可访问高权限字段。
- [ ] 本地 smoke 覆盖岗位标准、候选人召回、人才库事实查询、招聘报告生成。
