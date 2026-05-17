# 内网 Python 3.6.8 FastAPI 部署说明

## 部署目录

建议使用共享目录的独立子目录，不把虚拟环境和应用文件散放在根目录：

```bash
/workspace/devops/pkgs/ai/hr_mcp
/workspace/devops/pkgs/ai/hr_mcp/venv_py36
/workspace/devops/pkgs/ai/hr_mcp/app
/workspace/devops/pkgs/ai/hr_mcp/logs
```

先用服务运行用户验证可读写：

```bash
cd /workspace/devops/pkgs/ai
mkdir -p hr_mcp/_rw_test
echo ok > hr_mcp/_rw_test/write_test.txt
cat hr_mcp/_rw_test/write_test.txt
rm -rf hr_mcp/_rw_test
```

## 创建共享 venv

```bash
cd /workspace/devops/pkgs/ai/hr_mcp
python3 -m venv venv_py36
venv_py36/bin/pip install -r app/requirements-py36.txt
```

如果 `python3 -m venv` 不可用，先让运维确认 Python 3.6.8 环境是否带 `venv` 模块。

## 配置

复制示例配置，不要把真实密码和 token 提交到 git：

```bash
cp app/.env.intranet.example app/.env
cp app/config/auth_tokens.example.json app/config/auth_tokens.json
```

`.env` 中真实 MySQL 配置：

```env
HR_DATA_BACKEND=mysql
HR_DB_HOST=10.100.15.22
HR_DB_PORT=3306
HR_DB_USER=devops_r
HR_DB_PASSWORD=<内网真实密码>
HR_DB_NAME=devops
```

数据库侧必须先创建或确认：

```text
v_candidate_agent_safe
v_candidate_agent_privileged
```

真实库当前没有这两个 view，首次部署直接执行项目内 SQL 文件：

```bash
mysql -h 10.100.15.22 -P 3306 -u <db_dev_user> -p devops < app/sql/v_candidate_agent_safe.sql
mysql -h 10.100.15.22 -P 3306 -u <db_dev_user> -p devops < app/sql/v_candidate_agent_privileged.sql
```

执行后验证 view 可查、候选人唯一、safe/privileged 行数一致：

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

`total_rows` 必须等于 `distinct_candidates`，`safe_count` 必须等于 `privileged_count`。MCP 服务不自动创建或更新 view，只在 `/readyz` 检查两个 view 是否可查询。

## 启动

正式推荐 `systemd` 或已有进程托管；没有权限时可用 `nohup` 做临时联调：

```bash
cd /workspace/devops/pkgs/ai/hr_mcp/app
nohup ../venv_py36/bin/python -m hr_mcp > ../logs/hr_mcp.log 2>&1 &
```

`nohup` 只适合测试。长期运行建议交给 `systemd`，以便自动重启、统一日志和状态查看。

## 验证

```bash
curl http://127.0.0.1:8765/healthz
curl http://127.0.0.1:8765/readyz
curl -X POST http://127.0.0.1:8765/mcp \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

审计日志默认写入：

```text
runtime/audit/audit.jsonl
```
