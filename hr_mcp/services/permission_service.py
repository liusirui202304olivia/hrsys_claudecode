"""RBAC 与 ABAC 权限服务。

该文件集中判断角色能力、候选人行级范围和高权限字段访问资格。
HR_ADMIN 可访问全量候选人默认范围，RECRUITER、DEPARTMENT_MANAGER 和 INTERVIEWER 会按责任人、部门或面试关系过滤。
READONLY_VIEWER 只用于聚合统计，不允许获取候选人明细。
"""

from typing import Any, Dict, List, Optional, Set, Tuple, Union

from hr_mcp.models.context import IdentityContext


class PermissionService:
    def can_access_privileged_fields(self, identity: IdentityContext) -> bool:
        return identity.role == "HR_ADMIN" and bool(identity.access_reason)

    def candidate_query_scope(self, identity: IdentityContext) -> Dict[str, Any]:
        if identity.role == "HR_ADMIN":
            return {}
        if identity.role == "READONLY_VIEWER":
            return {"deny_all": True}
        if identity.role == "RECRUITER" and identity.user_id is not None:
            return {"role": "RECRUITER", "user_id": identity.user_id}
        if identity.role == "DEPARTMENT_MANAGER" and identity.department_id is not None:
            return {"role": "DEPARTMENT_MANAGER", "department_id": identity.department_id}
        if identity.role == "INTERVIEWER" and identity.user_id is not None:
            return {"role": "INTERVIEWER", "user_id": identity.user_id}
        return {"deny_all": True}

    def aggregate_query_scope(self, identity: IdentityContext) -> Dict[str, Any]:
        if identity.role == "READONLY_VIEWER":
            return {}
        return self.candidate_query_scope(identity)

    def filter_candidate_records(self, records: List[Dict[str, Any]], identity: IdentityContext) -> List[Dict[str, Any]]:
        if identity.role == "HR_ADMIN":
            return records
        if identity.role == "READONLY_VIEWER":
            return []
        if identity.role == "RECRUITER" and identity.user_id is not None:
            return [
                row for row in records
                if row.get("hr_id") == identity.user_id or self._follower_matches(row, identity.user_id)
            ]
        if identity.role == "DEPARTMENT_MANAGER" and identity.department_id is not None:
            return [row for row in records if row.get("proposed_department_id") == identity.department_id]
        if identity.role == "INTERVIEWER" and identity.user_id is not None:
            return [row for row in records if self._interviewer_matches(row, identity.user_id)]
        return []

    def _interviewer_matches(self, row: Dict[str, Any], user_id: int) -> bool:
        if row.get("interviewer_id") == user_id:
            return True
        interviewer_ids = row.get("interviewer_ids") or []
        if isinstance(interviewer_ids, str):
            interviewer_ids = [item.strip() for item in interviewer_ids.split(",") if item.strip()]
        return str(user_id) in {str(interviewer_id) for interviewer_id in interviewer_ids}

    def _follower_matches(self, row: Dict[str, Any], user_id: int) -> bool:
        if row.get("follower_id") == user_id:
            return True
        follower_ids = row.get("follower_ids") or []
        if isinstance(follower_ids, str):
            follower_ids = [item.strip() for item in follower_ids.split(",") if item.strip()]
        elif not isinstance(follower_ids, (list, tuple, set)):
            follower_ids = [follower_ids]
        return str(user_id) in {str(follower_id).strip() for follower_id in follower_ids}
