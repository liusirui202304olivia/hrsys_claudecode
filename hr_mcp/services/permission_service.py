"""RBAC 与 ABAC 权限服务。

该文件集中判断角色能力、候选人行级范围和高权限字段访问资格。
HR_ADMIN 可访问全量候选人默认范围，RECRUITER、DEPARTMENT_MANAGER 和 INTERVIEWER 会按责任人、部门或面试关系过滤。
READONLY_VIEWER 只用于聚合统计，不允许获取候选人明细。
"""

from hr_mcp.models.context import IdentityContext


class PermissionService:
    def can_access_privileged_fields(self, identity: IdentityContext) -> bool:
        return identity.role == "HR_ADMIN" and bool(identity.access_reason)

    def filter_candidate_records(self, records: list[dict], identity: IdentityContext) -> list[dict]:
        if identity.role == "HR_ADMIN":
            return records
        if identity.role == "READONLY_VIEWER":
            return []
        if identity.role == "RECRUITER" and identity.user_id is not None:
            return [row for row in records if row.get("hr_id") == identity.user_id or row.get("follower_id") == identity.user_id]
        if identity.role == "DEPARTMENT_MANAGER" and identity.department_id is not None:
            return [row for row in records if row.get("proposed_department_id") == identity.department_id]
        if identity.role == "INTERVIEWER" and identity.user_id is not None:
            return [row for row in records if row.get("interviewer_id") == identity.user_id]
        return []
