# Claude Code MCP over HTTP 接入说明

## 本地启动

在 `D:\hr_for_claudecode` 下运行：

```powershell
python -m hr_mcp
```

默认监听：`http://127.0.0.1:8765`。

可在 `.env` 中覆盖：

```env
HR_MCP_HOST=127.0.0.1
HR_MCP_PORT=8765
HR_DATA_BACKEND=dump
HR_GATEWAY_SHARED_SECRET=change-me-outside-git
```

P0 默认使用 SQL dump 验证链路：`hr_data_sample/devops_hr_user_data_0508_1.sql`。接内网 MySQL 时由服务端 `.env` 配置数据库连接，Claude Code CLI 不保存数据库账号和密码。

## MCP HTTP Endpoint

- `GET /healthz`：存活检查。
- `GET /readyz`：检查数据源、Markdown 标准库、审计存储。
- `POST /mcp`：MCP over HTTP JSON-RPC 入口。
- `GET /mcp/tools`：调试工具清单，仅管理员或调试角色。

## JSON-RPC 示例

工具清单：

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
```

获取岗位标准：

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "get_screening_policy",
    "arguments": {"position_query": "芯片建模工程师"}
  }
}
```

安全候选人召回：

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "search_candidate_safe_profiles",
    "arguments": {
      "filters": {"position_query": "芯片建模", "min_work_years": 3},
      "return_fields": ["name", "gender", "degree", "college", "major", "work_years", "skills", "proposed_join_date"],
      "limit": 20
    }
  }
}
```

高权限联系方式访问必须由 Gateway 加入：

```text
X-User-Role: HR_ADMIN
X-Access-Reason: 联系候选人安排面试
```

普通 Agent 推荐上下文不要请求 `mobile`、`email`、`phone`、`username`。

## Claude Code / ai_cli 配置要点

客户端只配置 MCP HTTP URL 和统一认证入口：

```json
{
  "mcpServers": {
    "hr-mcp-p0": {
      "transport": "http",
      "url": "https://<gateway-host>/mcp/hr/p0"
    }
  }
}
```

实际身份 header 由 Gateway 基于 SSO 会话注入；生产环境还应由 Gateway 注入 `X-Gateway-Secret`，HR MCP 服务端用 `HR_GATEWAY_SHARED_SECRET` 校验。客户端配置中不要出现数据库连接串、数据库用户名或数据库密码。

## P0 验收问题

- “筛一筛芯片建模工程师，推荐一部分人。”
- “库里各岗位候选人数量分布怎么样？”
- “生成一份应用软件开发工程师候选人池分析报告。”
