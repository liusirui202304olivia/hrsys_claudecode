"""RBAC 与 ABAC 权限服务。

该文件集中判断角色能力、候选人明细范围和高权限字段访问资格。
HR_ADMIN、RECRUITER、DEPARTMENT_MANAGER 和 INTERVIEWER 默认都可读取全库安全候选人画像。
READONLY_VIEWER 只用于聚合统计，不允许获取候选人明细；联系方式等高权限字段仍只允许 HR_ADMIN 带访问理由读取。
"""

from typing import Any, Dict, List

from hr_mcp.models.context import IdentityContext


class PermissionService:
    def can_access_privileged_fields(self, identity: IdentityContext) -> bool:
        return identity.role == "HR_ADMIN" and bool(identity.access_reason)

    def candidate_query_scope(self, identity: IdentityContext) -> Dict[str, Any]:
        if identity.role in {"HR_ADMIN", "RECRUITER", "DEPARTMENT_MANAGER", "INTERVIEWER"}:
            return {}
        if identity.role == "READONLY_VIEWER":
            return {"deny_all": True}
        return {"deny_all": True}

    def aggregate_query_scope(self, identity: IdentityContext) -> Dict[str, Any]:
        if identity.role == "READONLY_VIEWER":
            return {}
        return self.candidate_query_scope(identity)

    def filter_candidate_records(self, records: List[Dict[str, Any]], identity: IdentityContext) -> List[Dict[str, Any]]:
        if identity.role in {"HR_ADMIN", "RECRUITER", "DEPARTMENT_MANAGER", "INTERVIEWER"}:
            return records
        if identity.role == "READONLY_VIEWER":
            return []
        return []
