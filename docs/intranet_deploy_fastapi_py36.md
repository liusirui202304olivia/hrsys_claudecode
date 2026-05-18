# 内网 HR MCP 重新部署 Runbook

本文档用于把外网本地的新代码包重新部署到内网中心化 HR MCP 服务，并接入 Claude Code CLI。

当前架构边界：

- HR MCP/API 后端是安全数据服务层，不是 HR 业务 Agent。
- Claude Code CLI + Skill 是业务推理层，负责筛选、推荐、问答、分析和报告。
- 后端提供 6 个安全数据工具：候选人安全画像、批量详情、事实聚合、安全 SQL、Schema 描述、推荐结果保存。
- 开放式业务问题可以让 Agent 写安全 SQL，但 SQL 只能查询后端校验后的安全 view。

## 0. 固定路径

内网部署路径固定为：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
APP=$BASE/app
VENV=$BASE/venv_py36
LOGS=$BASE/logs
CONFIG=$BASE/config
DEPLOY=$BASE/deploy
```

目录结构：

```text
/workspace/devops/env_prod/service/ai/hr_mcp/
├── app/        # 当前发布版本代码
├── venv_py36/  # 共享 Python 虚拟环境
├── logs/       # nohup 日志、audit.jsonl、screening_results.jsonl、pid
├── config/     # auth_tokens.json
└── deploy/     # nohup/systemd/check 脚本
```

外网 Windows 本地路径固定为：

```text
D:\hr_for_claudecode
```

外网本地不能直连内网 MySQL，也不能直接 curl 内网服务。内网命令必须在 NoMachine/nx2 或内网研发机 shell 中执行。

不要在外网本地执行 MySQL、内网 curl、Claude Code 内网 MCP 注册等命令；这些步骤只在内网 shell 中执行。

## 1. 外网本地发布前检查

在 Git Bash 中执行：

```bash
cd /d/hr_for_claudecode
git status -sb
python -m pytest tests -q
python -m pytest tests/test_python36_compatibility.py -q
git diff --check
```

期望：

```text
145 passed
1 passed
```

如果 `git status -sb` 不干净，先确认改动是否都已提交。发布脚本要求工作树干净。

生成发布包：

```bash
bash ./deploy/package_release.sh
```

当前新代码对应的包名格式：

```text
D:\hr_for_claudecode\release\hr_mcp_release_<commit>.zip
```

例如当前发布包名会类似：

```text
D:\hr_for_claudecode\release\hr_mcp_release_<commit>.zip
```

如果你在 PowerShell 里执行，使用：

```powershell
& 'C:\Program Files\Git\bin\bash.exe' ./deploy/package_release.sh
```

## 2. 拷贝代码到内网

外网 Windows 本地使用 Git Bash 生成发布包：

```bash
cd /d/hr_for_claudecode
bash ./deploy/package_release.sh
```

不要在 Git Bash 里执行 `.\deploy\package_release.ps1`。反斜杠会被 Bash 当作转义字符，导致 PowerShell 脚本路径解析失败。

通过 NoMachine 把 zip 传到内网机器，例如：

```text
/workspace/devops/env_prod/service/ai/hr_mcp/hr_mcp_release_<commit>.zip
```

如果文件先到了 `~/Desktop`，再在内网 shell 执行：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
ZIP=<你实际上传的zip文件名>
mv ~/Desktop/$ZIP "$BASE/"
```

如果文件名不同，把命令中的 zip 名替换成实际文件名。

## 3. 确认内网目录权限

在内网机器执行：

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

如果 `Permission denied`，说明服务目录权限不够，需要让运维或目录负责人给当前部署用户写权限。

## 4. 替换内网 app 代码

先停旧服务：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
bash "$BASE/deploy/stop_hr_mcp_nohup.sh" || true
```

备份旧 app：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
TS=$(date +%Y%m%d_%H%M%S)
mv "$BASE/app" "$BASE/app_backup_$TS"
mkdir -p "$BASE/app"
```

解压新包：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
cd "$BASE/app"
ZIP=<你实际上传的zip文件名>
unzip "$BASE/$ZIP"
```

验证关键文件存在：

```bash
ls "$BASE/app"/hr_mcp "$BASE/app"/skills "$BASE/app"/deploy "$BASE/app"/requirements-py36.txt
grep -n "sqlparse" "$BASE/app/requirements-py36.txt"
```

期望能看到：

```text
sqlparse==0.4.4
```

## 5. 更新 Python 虚拟环境依赖

本次新代码新增了安全 SQL 解析依赖 `sqlparse==0.4.4`。内网使用公司私有 PyPI 源安装。

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
"$BASE/venv_py36/bin/python" -m pip install \
  --trusted-host pnexus01 \
  -i http://pnexus01:17081/repository/pypi/simple \
  -r "$BASE/app/requirements-py36.txt"
```

验证依赖：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
"$BASE/venv_py36/bin/python" -c "import fastapi, uvicorn, pymysql, sqlparse; print('ok')"
```

期望：

```text
ok
```

如果报 `No module named fastapi` 或 `No module named sqlparse`，说明依赖没有装进 `$BASE/venv_py36`，不要用系统 Python 启动服务。

如果 pip 连接 `pypi.org` 超时，说明没有走公司源，重新使用上面的 `pnexus01` 命令。

## 6. 数据库 view 状态

本次安全 SQL 工具没有新增 view 字段，因此如果内网已经成功创建过：

- `devops.v_candidate_agent_safe`
- `devops.v_candidate_agent_privileged`

通常不需要重建 view。

仍建议执行一次验证：

```bash
mysql -h 10.100.15.22 -P 3306 -u devops_r -p devops -e "
SELECT candidate_id FROM devops.v_candidate_agent_safe LIMIT 1;
SELECT candidate_id FROM devops.v_candidate_agent_privileged LIMIT 1;
SELECT COUNT(*) AS total_rows, COUNT(DISTINCT candidate_id) AS distinct_candidates
FROM devops.v_candidate_agent_safe;
SELECT COUNT(*) AS total_rows, COUNT(DISTINCT candidate_id) AS distinct_candidates
FROM devops.v_candidate_agent_privileged;
SELECT
  (SELECT COUNT(*) FROM devops.v_candidate_agent_safe) AS safe_count,
  (SELECT COUNT(*) FROM devops.v_candidate_agent_privileged) AS privileged_count;
"
```

通过标准：

- 两个 view 都能查询。
- 每个 view 的 `total_rows = distinct_candidates`。
- `safe_count = privileged_count`。
- safe view 不包含 `mobile/email`。
- privileged view 只比 safe view 多联系方式字段。

如果未来 SQL view 文件发生变化，再由数据库开发账号重新执行：

```bash
mysql -h 10.100.15.22 -P 3306 -u <db_dev_user> -p devops < "$BASE/app/sql/v_candidate_agent_safe.sql"
mysql -h 10.100.15.22 -P 3306 -u <db_dev_user> -p devops < "$BASE/app/sql/v_candidate_agent_privileged.sql"
```

## 7. 检查 `.env`

确认内网 `.env` 存在：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
ls -l "$BASE/.env"
```

内容至少包含：

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
chmod 600 "$BASE/.env"
```

注意：

- `HR_DATA_BACKEND` 必须显式是 `mysql`。
- 数据库密码只放 `.env`，不进入 release zip，不进入 git。
- Claude Code CLI 不保存数据库账号和密码。

## 8. 检查 token 配置

确认：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
ls -l "$BASE/config/auth_tokens.json"
chmod 600 "$BASE/config/auth_tokens.json"
```

P0 联调示例结构：

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

当前业务权限口径：

- `HR_ADMIN`：全库安全画像；联系方式字段需要访问理由。
- `RECRUITER`：全库安全画像；默认无联系方式。
- `DEPARTMENT_MANAGER`：全库安全画像；默认无联系方式。
- `INTERVIEWER`：全库安全画像；默认无联系方式。
- `READONLY_VIEWER`：只能看聚合统计，不能看候选人明细。

正式上线前应替换为飞书 SSO 或公司统一身份接口；测试 token 只用于内网联调。

## 9. 复制部署脚本

每次替换 app 后，同步部署脚本：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
cp "$BASE/app/deploy/"*.sh "$BASE/deploy/"
chmod +x "$BASE/deploy/"*.sh
```

## 10. 启动服务

临时联调用 nohup：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
bash "$BASE/deploy/start_hr_mcp_nohup.sh"
tail -f "$BASE/logs/hr_mcp.err"
```

健康检查：

```bash
curl -sS http://127.0.0.1:8765/healthz
curl -sS http://127.0.0.1:8765/readyz
```

期望：

```json
{"status":"ok"}
{"status":"ready"}
```

如果 `/readyz` 不是 ready，按顺序查：

1. `.env` 是否存在，权限是否可读。
2. `HR_DATA_BACKEND=mysql` 是否配置。
3. 数据库密码是否正确。
4. 两个 view 是否存在且 `devops_r` 能查。
5. `$BASE/venv_py36/bin/python` 是否能 import `pymysql`。
6. 查看 `$BASE/logs/hr_mcp.err`。

## 11. 新版 MCP Smoke

设置 token：

```bash
TOKEN=<replace-admin-token>
URL=http://127.0.0.1:8765
```

### 11.1 tools/list 必须看到 6 个工具

```bash
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

必须包含：

```text
search_candidate_safe_profiles
get_candidate_safe_detail_batch
query_talent_pool_facts
query_hr_safe_sql
describe_hr_safe_schema
save_screening_result
```

### 11.2 describe_hr_safe_schema

```bash
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"describe_hr_safe_schema","arguments":{}}}'
```

期望返回 `v_candidate_agent_safe` 字段列表。

### 11.3 安全 SQL 查询准备入职

```bash
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @- <<'JSON'
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"query_hr_safe_sql","arguments":{"purpose":"查询最近准备入职候选人","sql":"SELECT candidate_id, name, status, proposed_join_date, position_name FROM v_candidate_agent_safe WHERE proposed_join_date IS NOT NULL AND status NOT IN ('REJECTED', 'HIRED') ORDER BY proposed_join_date ASC LIMIT 20"}}}
JSON
```

期望返回：

```text
rows
row_count
columns
limit
view
fields
```

### 11.4 按姓名查人

```bash
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"search_candidate_safe_profiles","arguments":{"filters":{"name_query":"张"},"page_size":10}}}'
```

期望返回 `candidates`，且候选人里包含 `candidate_id` 和 `name`。

### 11.5 安全 SQL 禁止原表

```bash
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"query_hr_safe_sql","arguments":{"purpose":"验证禁止原表","sql":"SELECT id, name FROM hr_candidate LIMIT 10"}}}'
```

期望返回 JSON-RPC error，不能返回原表数据。

### 11.6 权限 smoke

普通角色请求联系方式应失败：

```bash
TOKEN=<replace-recruiter-token>
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"query_hr_safe_sql","arguments":{"purpose":"验证普通角色不能看联系方式","sql":"SELECT candidate_id, name, mobile FROM v_candidate_agent_privileged LIMIT 10"}}}'
```

管理员带访问理由才允许查 privileged view：

```bash
TOKEN=<replace-admin-token>
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"query_hr_safe_sql","arguments":{"purpose":"联系候选人安排面试","access_reason":"联系候选人安排面试","sql":"SELECT candidate_id, name, mobile FROM v_candidate_agent_privileged LIMIT 10"}}}'
```

## 12. 使用 check 脚本

```bash
export HR_MCP_TOKEN=<replace-admin-token>
export HR_MCP_URL=http://127.0.0.1:8765
bash /workspace/devops/env_prod/service/ai/hr_mcp/deploy/check_hr_mcp.sh
```

新版 check 脚本会检查：

- `/healthz`
- `/readyz`
- `tools/list`
- `query_talent_pool_facts`
- `describe_hr_safe_schema`
- `query_hr_safe_sql`

## 13. Claude Code CLI 接入

单用户命令行接入：

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

推荐 `.mcp.json`：

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

不要把真实 token 写进共享 `.mcp.json`。

## 14. Claude Code 验收问题

先确认 Claude Code 能看到 6 个 HR MCP 工具，然后测试：

```text
看看张三的信息。
最近一个月有哪些人准备入职？
库里各岗位候选人数量分布怎么样？
筛一筛芯片建模工程师，推荐一部分人。
生成一页应用软件开发工程师候选人池分析报告。
```

预期行为：

- 姓名查询能返回候选人姓名和 `candidate_id`。
- 准备入职问题默认按 `proposed_join_date`，并排除 `REJECTED`、`HIRED`。
- 开放问题可走 `query_hr_safe_sql`，但只能查安全 view。
- 推荐、分析、报告由 Skill 生成，不由后端生成。
- 普通用户看不到联系方式。
- 审计日志记录 user_id、role、tool_name、字段请求、错误类型。

## 15. 常见问题

### `No module named sqlparse`

新代码依赖没有装进 venv。执行：

```bash
BASE=/workspace/devops/env_prod/service/ai/hr_mcp
"$BASE/venv_py36/bin/python" -m pip install \
  --trusted-host pnexus01 \
  -i http://pnexus01:17081/repository/pypi/simple \
  -r "$BASE/app/requirements-py36.txt"
```

### `tools/list` 不是 6 个工具

说明服务还在跑旧代码。确认：

```bash
ps -ef | grep hr_mcp
cat "$BASE/logs/hr_mcp.pid"
```

停掉旧进程后重新启动。

### `/readyz` not ready

通常是 `.env`、数据库连接、view 不存在、权限不足或 venv 依赖问题。先看：

```bash
tail -200 "$BASE/logs/hr_mcp.err"
```

### 安全 SQL 查 `hr_candidate` 失败

这是正确行为。开放式 SQL 只能查：

```text
v_candidate_agent_safe
v_candidate_agent_privileged
```

其中 privileged view 只允许 `HR_ADMIN + access_reason`。

### 准备入职问题结果不符合预期

先确认使用口径：

- 准备入职：`proposed_join_date`
- 被拒时间：`status='REJECTED'` 时使用 `update_time`
- 最近状态变化：`update_time`
- 新增候选人：`create_time`

Skill 回答时必须说明时间口径。

## 16. 全公司试运行 Gate

扩大试点前必须满足：

- 服务由 systemd 或等效方式托管。
- `.env` 和 `auth_tokens.json` 权限为 600。
- token 发放、撤销、登记流程明确。
- 审计日志可查。
- 安全 SQL 禁止原表和危险语句的 smoke 已通过。
- 普通用户看不到联系方式。
- DB 账号后续最好收敛为只对安全 view 有 SELECT 权限。
- 有回滚方案：停服务、撤 token、恢复上一个 release zip。
