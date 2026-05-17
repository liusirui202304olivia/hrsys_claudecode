# 内网 Python 3.6.8 FastAPI HTTP-MCP 部署 Runbook

本文档用于完成「内网部署 -> 接入 Claude Code CLI -> 小范围试点 -> 全公司可用」全流程。
HR MCP/API 服务是中心化安全数据服务层，不是 HR 业务 Agent；筛选、推荐、问答、分析和报告生成由 Claude Code CLI Skill 完成。

## 0. 固定目录

统一部署到：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
APP=$BASE/app
VENV=$BASE/venv_py36
LOGS=$BASE/logs
CONFIG=$BASE/config
DEPLOY=$BASE/deploy
```

目录含义：

```text
/workspace/devops/env_prod/service/ai/hr_mcp/
├── app/        # 项目代码
├── venv_py36/  # Python 3.6 共享虚拟环境
├── logs/       # stdout/stderr、audit.jsonl、screening_results.jsonl、pid
├── config/     # auth_tokens.json
└── deploy/     # systemd/nohup/check 脚本
```

## 1. 验证目录可写

在内网部署机器上用服务运行用户执行：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
mkdir -p "$BASE"/{app,logs,config,deploy}
echo ok > "$BASE/logs/write_test.txt"
cat "$BASE/logs/write_test.txt"
rm "$BASE/logs/write_test.txt"
```

期望输出：

```text
ok
```

排查：

- `Permission denied`：找运维给服务运行用户开 `/workspace/devops/env_prod/service/ai/hr_mcp` 写权限。
- `No such file or directory`：先确认 `/workspace/devops/env_prod/service/ai` 是否存在。
- 目录不应退回个人 home；这是全公司共用的中心化服务目录。

## 2. 拷贝代码

推荐直接在 `app/` 目录拉取已验证 commit：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
cd "$BASE/app"
git clone <repo-url> .
git checkout <已验证commit>
```

如果不能 git clone，可以离线拷贝项目，但必须排除：

```text
.git/
.pytest_cache/
__pycache__/
.env
logs/
runtime/
venv_py36/
```

验证：

```bash
cd /workspace/devops/env_prod/service/ai/hr_mcp/app
python3 --version
ls requirements-py36.txt hr_mcp sql deploy
```

期望 Python：

```text
Python 3.6.8
```

## 3. 创建共享虚拟环境

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
python3 -m venv "$BASE/venv_py36"
"$BASE/venv_py36/bin/python" -m pip install --upgrade "pip==21.3.1"
"$BASE/venv_py36/bin/python" -m pip install -r "$BASE/app/requirements-py36.txt"
```

验证依赖：

```bash
"$BASE/venv_py36/bin/python" -c "import fastapi, uvicorn, pymysql; print('ok')"
```

期望：

```text
ok
```

如果 pip 不能联网：

```bash
# 在能联网且同为 Python 3.6 的机器准备离线包
python3 -m pip download -r requirements-py36.txt -d wheelhouse_py36

# 拷贝 wheelhouse_py36 到 $BASE/app 后安装
"$BASE/venv_py36/bin/python" -m pip install --no-index --find-links "$BASE/app/wheelhouse_py36" -r "$BASE/app/requirements-py36.txt"
```

## 4. 创建数据库安全视图

真实库当前没有 `v_candidate_agent_safe` 和 `v_candidate_agent_privileged`，首次部署由数据库开发账号执行项目 SQL：

```bash
mysql -h 10.100.15.22 -P 3306 -u <db_dev_user> -p devops < /workspace/devops/env_prod/service/ai/hr_mcp/app/sql/v_candidate_agent_safe.sql
mysql -h 10.100.15.22 -P 3306 -u <db_dev_user> -p devops < /workspace/devops/env_prod/service/ai/hr_mcp/app/sql/v_candidate_agent_privileged.sql
```

执行后验证：

```sql
SELECT candidate_id FROM devops.v_candidate_agent_safe LIMIT 1;
SELECT candidate_id FROM devops.v_candidate_agent_privileged LIMIT 1;

SELECT COUNT(*) AS total_rows, COUNT(DISTINCT candidate_id) AS distinct_candidates
FROM devops.v_candidate_agent_safe;

SELECT COUNT(*) AS total_rows, COUNT(DISTINCT candidate_id) AS distinct_candidates
FROM devops.v_candidate_agent_privileged;

SELECT
  (SELECT COUNT(*) FROM devops.v_candidate_agent_safe) AS safe_count,
  (SELECT COUNT(*) FROM devops.v_candidate_agent_privileged) AS privileged_count;
```

通过标准：

- 两个 view 都能查询。
- 每个 view 的 `total_rows = distinct_candidates`。
- `safe_count = privileged_count`。
- `v_candidate_agent_safe` 不包含 `mobile/email`。
- `v_candidate_agent_privileged` 只比 safe view 多候选人联系方式字段。

## 5. 写内网 `.env`

创建 `/workspace/devops/env_prod/service/ai/hr_mcp/.env`：

```bash
HR_MCP_HOST=0.0.0.0
HR_MCP_PORT=8765
HR_DATA_BACKEND=mysql

HR_AUTH_TOKENS_PATH=/workspace/devops/env_prod/service/ai/hr_mcp/config/auth_tokens.json
HR_AUDIT_PATH=/workspace/devops/env_prod/service/ai/hr_mcp/logs/audit.jsonl
HR_RESULT_PATH=/workspace/devops/env_prod/service/ai/hr_mcp/logs/screening_results.jsonl
HR_ALLOWED_IP_CIDRS=127.0.0.1/32,10.0.0.0/8
HR_RATE_LIMIT_PER_MINUTE=60
HR_MAX_REQUEST_BYTES=1048576

HR_DB_HOST=10.100.15.22
HR_DB_PORT=3306
HR_DB_USER=devops_r
HR_DB_PASSWORD=<真实密码只写这里>
HR_DB_NAME=devops
```

权限：

```bash
chmod 600 /workspace/devops/env_prod/service/ai/hr_mcp/.env
```

注意：

- `HR_DATA_BACKEND` 必须是 `mysql`，不能省略。
- 数据库密码只写内网 `.env`，不要提交 git。
- Claude Code CLI 不保存数据库连接串、用户名或密码。

## 6. 写 token 配置

创建 `/workspace/devops/env_prod/service/ai/hr_mcp/config/auth_tokens.json`：

```json
{
  "tokens": {
    "replace-admin-token": {
      "user_id": "1",
      "user_name": "HR Admin",
      "role": "HR_ADMIN",
      "department_id": ""
    },
    "replace-recruiter-token": {
      "user_id": "42",
      "user_name": "Recruiter Test",
      "role": "RECRUITER",
      "department_id": ""
    },
    "replace-readonly-token": {
      "user_id": "99",
      "user_name": "Readonly Test",
      "role": "READONLY_VIEWER",
      "department_id": ""
    }
  }
}
```

权限：

```bash
chmod 600 /workspace/devops/env_prod/service/ai/hr_mcp/config/auth_tokens.json
```

说明：

- P0 联调阶段每个试点用户一个 token。
- 用户身份和角色只信任服务端 token 映射。
- 客户端传 `X-User-Role: HR_ADMIN` 不会提权。
- 正式上线前应替换为飞书 SSO 或公司统一身份接口。

## 7. 临时启动与停止

先复制部署脚本：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
cp "$BASE/app/deploy/"*.sh "$BASE/deploy/"
```

启动：

```bash
bash /workspace/devops/env_prod/service/ai/hr_mcp/deploy/start_hr_mcp_nohup.sh
tail -f /workspace/devops/env_prod/service/ai/hr_mcp/logs/hr_mcp.err
```

启动脚本会设置 `HR_MCP_ENV_PATH=/workspace/devops/env_prod/service/ai/hr_mcp/.env`，由 Python 服务自己读取配置文件；脚本不会 `source` 含数据库密码的 `.env`。

停止：

```bash
bash /workspace/devops/env_prod/service/ai/hr_mcp/deploy/stop_hr_mcp_nohup.sh
```

`nohup` 只用于联调。全公司推广前必须交给 `systemd` 或等效进程管理托管。

## 8. 健康检查与 MCP Smoke

```bash
curl -sS http://127.0.0.1:8765/healthz
curl -sS http://127.0.0.1:8765/readyz
```

期望：

```json
{"status":"ok"}
{"status":"ready"}
```

执行完整检查脚本：

```bash
export HR_MCP_TOKEN=<replace-admin-token>
bash /workspace/devops/env_prod/service/ai/hr_mcp/deploy/check_hr_mcp.sh
```

如果服务不是 `127.0.0.1:8765`，先设置：

```bash
export HR_MCP_URL=http://<服务机器IP>:<端口>
```

如果 `/readyz` 不是 ready，按顺序排查：

1. `.env` 是否存在且权限正确。
2. `HR_DATA_BACKEND=mysql` 是否配置。
3. `HR_DB_PASSWORD` 是否正确。
4. `devops_r` 是否能连 `10.100.15.22:3306/devops`。
5. 两个 view 是否已创建且能查。
6. `devops_r` 是否有 `SELECT` 和 `SHOW VIEW`。
7. 查看 `logs/hr_mcp.err`。

## 9. systemd 正式托管

如果有 systemd 权限：

```bash
sudo cp /workspace/devops/env_prod/service/ai/hr_mcp/app/deploy/hr-mcp.service /etc/systemd/system/hr-mcp.service
sudo systemctl daemon-reload
sudo systemctl enable hr-mcp
sudo systemctl start hr-mcp
sudo systemctl status hr-mcp
```

`hr-mcp.service` 同时配置了 `EnvironmentFile=/workspace/devops/env_prod/service/ai/hr_mcp/.env` 和 `HR_MCP_ENV_PATH`；前者方便 systemd 注入环境变量，后者保证 Python 服务能按同一份配置文件读取运行配置。

查看日志：

```bash
journalctl -u hr-mcp -f
```

`systemd` 模式使用 journal，避免旧 systemd 不支持文件 append 输出导致服务启动失败。`nohup` 临时模式才会写 `logs/hr_mcp.out` 和 `logs/hr_mcp.err`。

如果服务账号不是 `marc`，先修改 `deploy/hr-mcp.service` 中的：

```ini
User=marc
Group=marc
```

## 10. Claude Code CLI 接入

单用户命令行添加：

```bash
export HR_MCP_URL=http://<服务机器IP>:8765
export HR_MCP_TOKEN=<分配给当前用户的token>

claude mcp add --transport http hr-mcp "$HR_MCP_URL/mcp" \
  --header "Authorization: Bearer $HR_MCP_TOKEN"
```

验证：

```bash
claude mcp list
```

推荐 `.mcp.json` 使用环境变量：

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

不要把真实 token 写入共享 `.mcp.json`。

## 11. Skill 验收

Claude Code CLI 侧需要可用：

```text
skills/hr-talent-intelligence/
skills/hr-candidate-screening/
skills/hr-talent-database-qa/
skills/hr-talent-analysis/
skills/hr-recruitment-report/
```

职责：

- `hr-candidate-screening`：基于岗位 Markdown 标准和安全候选人画像做推荐。
- `hr-talent-database-qa`：做事实问答，不生成推荐结论。
- `hr-talent-analysis`：分析候选池结构、岗位分布、状态分布、来源分布。
- `hr-recruitment-report`：生成 HR 汇报/PPT 型报告页。
- `hr-talent-intelligence`：总入口，只做意图路由。

当前支持六类岗位：

- 后端工程师，即数据库里的数字后端设计工程师。
- SOC设计工程师。
- 原型验证工程师。
- 芯片建模工程师，即数据库中的 CPU性能建模工程师。
- 应用软件开发工程师。
- AI芯片工程师，即数据库中的 AI芯片开发工程师。

验收问题：

```text
库里各岗位候选人数量分布怎么样？
筛一筛芯片建模工程师，推荐一部分人。
生成一页应用软件开发工程师候选人池分析报告。
```

## 12. 全公司推广 Gate

推广前必须满足：

- systemd 或等效托管已完成。
- 日志轮转已配置。
- token 发放、撤销、登记流程明确。
- 数据库 view 已由 DB 同事验证。
- `.env` 和 `auth_tokens.json` 权限是 600。
- 审计日志中能看到 user_id、role、tool_name、字段请求、错误类型。
- 有回滚方案：停服务、撤 token、保留日志、回退 commit。
