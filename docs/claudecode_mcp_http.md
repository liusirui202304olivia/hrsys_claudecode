# Claude Code MCP over HTTP 接入说明

## 服务边界

HR MCP/API 后端是 HR 安全数据服务层，不是 HR 业务 Agent。它只向 Claude Code CLI / Agent 提供安全、受控、可审计的数据能力。

Claude Code CLI + 项目内 Skill 是 HR 业务推理与执行层，负责基于岗位 Markdown 标准完成筛选、推荐、自然语言问答、招聘分析和报告生成。

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
HR_DATA_BACKEND=mysql
HR_AUTH_TOKENS_PATH=config/auth_tokens.json
```

`HR_DATA_BACKEND` 必须显式配置。内网真实联调使用 `mysql`；`dump` 只允许作为本地测试 fixture 显式配置，服务不能在未配置时自动回退到 dump。接内网 MySQL 时由服务端 `.env` 配置数据库连接，Claude Code CLI 不保存数据库账号和密码。

## MCP HTTP Endpoint

- `GET /healthz`：存活检查。
- `GET /readyz`：检查数据源、审计存储。
- `POST /mcp`：MCP over HTTP JSON-RPC 入口。
- `GET /mcp/tools`：调试工具清单，仅管理员或调试角色。

## MCP Tools

后端只暴露 4 个安全数据工具：

- `search_candidate_safe_profiles`：受控召回候选人安全画像。
- `get_candidate_safe_detail_batch`：按候选人 ID 批量读取安全详情。
- `query_talent_pool_facts`：返回 count、岗位分布、状态分布、来源分布等事实数据。
- `save_screening_result`：保存 Claude Code Agent 已生成的推荐结果。

后端不提供以下业务推理工具：

- 岗位标准读取：由项目内 Skill 直接读取 `standard_markdown/xiaoman.md` 和 `standard_markdown/yihai.md`。
- 候选人筛选推荐：由 Claude Code Agent + Skill 完成。
- 自然语言问答：由 Claude Code Agent + Skill 调用数据工具后组织回答。
- 招聘分析和报告生成：由 Claude Code Agent + Skill 完成。

## 项目内 Skill 结构

Skill 按业务任务类型拆分，不按工具调用动作拆分：

```text
skills/hr-talent-intelligence/SKILL.md        HR Talent Intelligence Skill 总入口
skills/hr-candidate-screening/SKILL.md        Candidate Screening Skill 候选人筛选推荐
skills/hr-talent-database-qa/SKILL.md         Talent Database QA Skill 人才库业务问答
skills/hr-talent-analysis/SKILL.md            Talent Analysis Skill 招聘数据分析
skills/hr-recruitment-report/SKILL.md         Recruitment Report Skill 招聘汇报/PPT 页生成
```

总入口只做任务路由；四个业务 Skill 负责各自业务流程。不要把筛选推荐、问答、分析、报告写成一个超大 Skill，也不要把读取标准、读取候选人、统计数量、保存结果这些工具动作拆成独立 Skill。

招聘报告 Skill 的默认产物不是普通长文，而是 HR 汇报/PPT 型页面内容，包括招聘漏斗分析、候选池结构分析、周期招聘进展、重点岗位推进页。每页应包含核心结论、关键指标卡、图表建议、数据口径、业务解读和行动建议。

六类已确认推荐标准：

- `standard_markdown/xiaoman.md`：后端工程师（数据库岗位名：数字后端设计工程师）、SOC设计工程师、原型验证工程师。
- `standard_markdown/yihai.md`：芯片建模工程师（数据库岗位名：CPU性能建模工程师）、应用软件开发工程师、AI芯片工程师（数据库岗位名：AI芯片开发工程师）。

## JSON-RPC 示例

工具清单：

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
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
      "filters": {"position_query": "CPU性能建模工程师", "min_work_years": 3},
      "return_fields": ["candidate_id", "name", "gender", "degree", "college", "major", "work_years", "skills", "proposed_join_date"],
      "page_size": 20
    }
  }
}
```

`search_candidate_safe_profiles` 返回的是分页结果：

```json
{
  "candidates": [],
  "total_count": 128,
  "has_more": true,
  "next_cursor": "opaque-cursor",
  "page_size": 20
}
```

`total_count` 是全量匹配数量，不受当前页大小影响。`page_size` 只限制单次返回给 Agent 的候选人数量；需要更多候选人时用 `next_cursor` 继续翻页。

事实查询：

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "query_talent_pool_facts",
    "arguments": {
      "metrics": ["count"],
      "filters": {"position_query": "应用软件开发工程师"},
      "group_by": ["status", "source_name"]
    }
  }
}
```

保存 Agent 推荐结果：

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "tools/call",
  "params": {
    "name": "save_screening_result",
    "arguments": {
      "task_id": "screen-20260516-001",
      "standard_ref": "standard_markdown/yihai.md#CPU性能建模工程师",
      "recommended_candidates": [
        {
          "candidate_id": 123,
          "recommend_reason": "项目经历包含性能建模和 C++ 系统能力，符合标准中的核心经验要求。",
          "risk_points": ["需要面试确认项目主导性", "需要确认 gem5 经验深度"]
        }
      ]
    }
  }
}
```

高权限联系方式访问必须带访问理由：

```text
X-Access-Reason: 联系候选人安排面试
```

普通 Agent 推荐上下文不要请求 `mobile`、`email`、`phone`、`username`。

## Claude Code / ai_cli 配置要点

客户端只配置 MCP HTTP URL 和统一认证入口：

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

当前无 API Gateway。身份由 HR MCP 服务端根据 Bearer token 映射，客户端配置中不要出现数据库连接串、数据库用户名或数据库密码。测试 token 仅用于内网联调，正式上线前应替换为飞书 SSO 或公司统一用户接口。

## P0 验收问题

这些问题由 Claude Code Skill 完成推理，并调用后端 4 个数据工具取数或保存：

- “筛一筛芯片建模工程师，推荐一部分人。”
- “库里各岗位候选人数量分布怎么样？”
- “生成一份应用软件开发工程师候选人池分析报告，用 PPT 汇报页结构展示。”
- “做一页芯片建模工程师招聘漏斗分析，说明各阶段转化率和流失原因。”
