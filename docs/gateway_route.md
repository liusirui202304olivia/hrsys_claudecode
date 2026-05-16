# HR MCP/API Gateway Route

## 目标链路

Claude Code CLI / ai_cli 只连接公司 API Gateway，不持有数据库账号，不直连 MySQL，不生成自由 SQL。

请求链路：

`Claude Code CLI / ai_cli -> API Gateway -> HR MCP/API Service -> 受控服务层 -> SQL 人才数据库`

## Gateway 路由

- 外部路径：`https://<gateway-host>/mcp/hr/p0`
- 内部上游：`http://<hr-mcp-host>:8765/mcp`
- 健康检查：`GET http://<hr-mcp-host>:8765/healthz`
- 就绪检查：`GET http://<hr-mcp-host>:8765/readyz`
- 调试工具清单：`GET http://<hr-mcp-host>:8765/mcp/tools`，仅 `HR_ADMIN` 或 `MCP_DEBUG` 角色。
- 审计查询：`POST http://<hr-mcp-host>:8765/internal/audit/query`，仅 `HR_ADMIN` 或 `MCP_DEBUG` 角色。

## Header Contract

Gateway 必须透传以下 header：

- `X-Request-Id`：请求 ID。
- `X-Trace-Id`：链路追踪 ID。
- `X-User-Id`：SSO 用户 ID。
- `X-User-Name`：SSO 用户姓名。
- `X-User-Role`：HR MCP 角色，取值建议为 `HR_ADMIN`、`RECRUITER`、`DEPARTMENT_MANAGER`、`INTERVIEWER`、`READONLY_VIEWER`。
- `X-Department-Id`：用户所属部门 ID，用于部门范围 ABAC。
- `X-Client-Id`：客户端 ID，例如 `claudecode`、`ai_cli`。
- `X-Access-Reason`：访问高权限字段时必填，并写入审计日志。

## 权限模型

默认 Agent 可见字段只包含已确认字段。候选人 `name`、`gender`、`proposed_join_date` 按原文返回，不掩码。

高权限字段：

- `hr_candidate.mobile`
- `hr_candidate.email`
- `sys_user.phone`
- `sys_user.email`
- `sys_user.username`

访问高权限字段必须同时满足：

1. `X-User-Role=HR_ADMIN`。
2. `X-Access-Reason` 非空。
3. 工具调用经过 `candidate_safe_view_service.py` 和 `field_policy.py`。

## Gateway 侧建议

- 在 Gateway 完成 HTTPS、SSL 终止和 SSO 鉴权。
- 对 `/mcp/hr/p0` 设置用户、设备、IP 访问控制。
- 对 `POST /mcp` 做请求体大小限制和全局限流。
- 记录 Gateway 请求日志，但不要记录高权限字段值。
- 禁止把数据库账号、密码、SQL 连接串注入 Claude Code CLI 配置。
