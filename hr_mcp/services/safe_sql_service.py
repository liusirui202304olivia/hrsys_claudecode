"""开放式安全 SQL 查询服务。

该文件为 Claude Code Agent 提供受控的自由查询入口：Agent 可以写 SQL 表达开放业务问题，
但 SQL 必须先经过安全策略校验，且只能查询候选人安全视图和字段白名单允许的字段。
服务本身不生成推荐、问答结论、分析结论或报告内容，只返回结构化数据和查询元数据供 Skill 使用。
"""

from typing import Any, Dict, List, Optional, Set, Tuple, Union

from hr_mcp.models.context import IdentityContext
from hr_mcp.security.field_policy import FieldPolicy
from hr_mcp.security.safe_sql_policy import SafeSqlPolicy, SafeSqlValidationError


class SafeSqlService:
    def __init__(self, repository, field_policy: FieldPolicy):
        self.repository = repository
        self.policy = SafeSqlPolicy(field_policy)

    def query(self, sql: str, identity: IdentityContext) -> Dict[str, Any]:
        plan = self.policy.validate(sql, identity)
        rows = self.repository.execute_safe_sql(plan.sql)
        return {
            "rows": rows,
            "row_count": len(rows),
            "columns": sorted(rows[0].keys()) if rows else [],
            "limit": plan.limit,
            "view": plan.view_name,
            "fields": plan.fields,
            "privileged": plan.privileged,
            "sql_executed": plan.sql,
        }

    def describe_schema(self, identity: IdentityContext) -> Dict[str, Any]:
        return self.policy.describe_schema(identity)
