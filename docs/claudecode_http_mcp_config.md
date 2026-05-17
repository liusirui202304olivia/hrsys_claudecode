# Claude Code CLI HTTP MCP 配置

Claude Code CLI 直接连接中心化 HR MCP 服务，不使用 stdio-MCP。

## 命令行添加

```bash
claude mcp add --transport http hr-mcp "$HR_MCP_URL/mcp" \
  --header "Authorization: Bearer $HR_MCP_TOKEN"
```

## `.mcp.json` 配置

推荐使用环境变量，避免把 token 写死在配置文件里：

```json
{
  "mcpServers": {
    "hr-mcp": {
      "type": "http",
      "url": "${HR_MCP_URL}/mcp",
      "headers": {
        "Authorization": "Bearer ${HR_MCP_TOKEN}"
      }
    }
  }
}
```

## 安全边界

- Claude Code CLI 不保存数据库账号、密码或连接串。
- 用户身份由服务端 token 映射，不信任客户端自报的 `X-User-Role` 或 `X-User-Id`。
- 高权限字段访问需要 `X-Access-Reason`，或工具参数中的 `access_reason`。
- 测试 token 只用于内网联调，正式上线前应替换为飞书 SSO 或公司统一用户接口。

## 验收问题

```text
筛一筛芯片建模工程师，推荐一部分人。
库里各岗位候选人数量分布怎么样？
生成一页应用软件开发工程师候选人池分析报告。
```
