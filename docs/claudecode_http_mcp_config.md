# Claude Code CLI HTTP MCP 配置

Claude Code CLI 直接连接中心化 HR MCP 服务，不使用 stdio-MCP。

内网服务默认部署目录是 `/workspace/devops/env_prod/service/ai/hr_mcp`，HTTP 地址由部署机器和端口决定，例如：

```bash
export HR_MCP_URL=http://<服务机器IP>:8765
export HR_MCP_TOKEN=<当前用户自己的token>
```

服务端实际读取 `/workspace/devops/env_prod/service/ai/hr_mcp/.env`。`HR_MCP_ENV_PATH` 只在服务启动脚本和 systemd unit 中使用，普通 Claude Code CLI 用户不需要配置它。

如果外网本地不能访问内网服务地址，下面的 `claude mcp add` 和验收问题必须在 NoMachine/nx2 或内网 Claude Code CLI 环境执行。本地 Git Bash 只负责执行 `bash ./deploy/package_release.sh` 打包代码和传输 release zip。

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
- 不要把真实 token 写入共享 `.mcp.json`；优先用 `${HR_MCP_TOKEN}` 环境变量。

## 验收问题

```text
筛一筛芯片建模工程师，推荐一部分人。
库里各岗位候选人数量分布怎么样？
生成一页应用软件开发工程师候选人池分析报告。
```
