# 内网 HR MCP Lark 部署 Runbook

本文档用于把 `D:\hr_for_lark` 部署到内网 `10.100.15.22`，作为飞书龙虾智能体 / OpenClaw wrapper 使用的独立 HR MCP/FastAPI 服务。

这套服务不替代之前 Claude Code 使用的 `hr-mcp` 服务。两套服务必须并存：

```text
Claude Code HR MCP:
  base:    /workspace/devops/env_prod/service/ai/hr_mcp
  service: hr-mcp.service
  port:    8765

Feishu / OpenClaw HR MCP:
  base:    /workspace/devops/env_prod/service/ai/hr_mcp_lark
  service: hr-mcp-lark.service
  port:    8766
```

HR MCP/API 后端是安全数据服务层，不是 HR 业务 Agent。飞书龙虾智能体和 OpenClaw wrapper 承担业务 runtime；HR MCP 只提供安全数据工具、safe views、字段白名单、权限和审计。

## 1. 部署边界

生产目录固定为：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp_lark
```

外网 Windows 本地只负责打包和传输 release zip。内网 MySQL、内网 curl、服务启动、smoke 验证只在 NoMachine/nx2 内网 shell 中执行。

不要覆盖或停止既有 Claude Code 服务目录 `/workspace/devops/env_prod/service/ai/hr_mcp`、`hr-mcp.service` 或 `8765` 端口。

## 2. 打包代码

在外网 Windows 本地 Git Bash 中执行：

```bash
cd /d/hr_for_lark
bash ./deploy/package_release.sh
```

脚本要求工作区 clean，并用 `git archive --format=zip` 生成 `hr_mcp_lark_release_<commit>.zip`。不要在 PowerShell 手写反斜杠续行；反斜杠会被 Bash 当作转义字符。

## 3. 传输与展开

把 release zip 通过 NoMachine 传到内网后，在内网 shell 中执行：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp_lark
mkdir -p "$BASE/app" "$BASE/config" "$BASE/logs"
unzip -o "$BASE/hr_mcp_lark_release_<commit>.zip" -d "$BASE/app"
```

## 4. 内网配置

`.env` 放在：

```bash
/workspace/devops/env_prod/service/ai/hr_mcp_lark/.env
```

关键配置：

```text
HR_MCP_HOST=0.0.0.0
HR_MCP_PORT=8766
HR_DATA_BACKEND=mysql
HR_OPENCLAW_SERVICE_TOKENS=<secret-managed-wrapper-token>
HR_FEISHU_IDENTITIES_PATH=/workspace/devops/env_prod/service/ai/hr_mcp_lark/config/feishu_identities.json
HR_AUDIT_PATH=/workspace/devops/env_prod/service/ai/hr_mcp_lark/logs/audit.jsonl
HR_RESULT_PATH=/workspace/devops/env_prod/service/ai/hr_mcp_lark/logs/screening_results.jsonl
HR_ALLOWED_IP_CIDRS=127.0.0.1/32,10.0.0.0/8
HR_TRUSTED_PROXY_CIDRS=127.0.0.1/32
HR_RATE_LIMIT_PER_MINUTE=60
HR_MAX_REQUEST_BYTES=1048576

HR_DB_HOST=10.100.15.22
HR_DB_PORT=3306
HR_DB_USER=devops_r
HR_DB_PASSWORD=<replace-in-intranet-env>
HR_DB_NAME=devops
```

真实 service token 应由平台 Secret 或统一配置中心注入。`feishu_identities.json` 只做 open_id 到公司用户身份映射，不能绕过现有权限链路。

示例映射：

```json
{
  "open_ids": {
    "ou_xxx": {
      "company_user_id": 42,
      "user_name": "HR User",
      "role": "RECRUITER",
      "department_id": 7,
      "enabled": true,
      "data_scope": "existing_scope_label"
    }
  }
}
```

文件权限：

```bash
chmod 600 "$BASE/.env"
chmod 600 "$BASE/config/feishu_identities.json"
```

## 5. Safe Views

内网 MySQL 必须存在 6 个 approved safe views：

```text
v_candidate_agent_safe
v_candidate_agent_privileged
v_candidate_interview_safe
v_candidate_interview_evaluate_safe
v_candidate_interview_question_safe
v_candidate_screen_evaluate_safe
```

不要只沿用旧版两个候选人 view；否则 `/readyz` 会失败，飞书侧也查不到面试评价。

## 6. 启动服务

nohup 启动：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp_lark
bash "$BASE/app/deploy/start_hr_mcp_lark_nohup.sh"
tail -f "$BASE/logs/hr_mcp_lark.err"
```

systemd 部署使用 Lark 专用 unit，不覆盖既有 `hr-mcp.service`：

```bash
sudo cp "$BASE/app/deploy/hr-mcp-lark.service" /etc/systemd/system/hr-mcp-lark.service
sudo systemctl daemon-reload
sudo systemctl enable --now hr-mcp-lark.service
sudo systemctl status hr-mcp-lark.service
```

## 7. Smoke 验证

在内网 shell 设置 wrapper service token 和一个已映射的 Feishu open_id：

```bash
export HR_OPENCLAW_SERVICE_TOKEN=<service-token>
export HR_FEISHU_OPEN_ID=<mapped-open-id>
export HR_OPENCLAW_ACCOUNT_ID=<account-id>
bash /workspace/devops/env_prod/service/ai/hr_mcp_lark/app/deploy/check_hr_mcp_lark.sh
```

脚本默认访问 `http://127.0.0.1:8766`，会验证：

- `/healthz`
- `/readyz`
- `tools/list`
- `query_talent_pool_facts`
- `describe_hr_safe_schema`
- `query_hr_safe_sql`
- 面试评价、面试题目聚合、初筛评价 safe views

## 8. 安全检查

- 不提交真实 service token、真实 open_id 映射或生产 `.env`。
- `X-Feishu-Open-Id` 只有在 service token、可信 IP/代理链路、`X-Source-Runtime=openclaw_feishu` 全部通过后才可信。
- `X-User-Id`、`X-User-Role`、`X-Department-Id` 不可信。
- `HR_TRUSTED_PROXY_CIDRS` 必须覆盖真实 Nginx/API Gateway/反向代理链路。
- `/mcp` body 中出现身份或鉴权字段会被 HTTP 层拒绝并审计。
- 不覆盖 `/workspace/devops/env_prod/service/ai/hr_mcp`、`hr-mcp.service` 或 `8765`；它们留给原 Claude Code HR MCP。
