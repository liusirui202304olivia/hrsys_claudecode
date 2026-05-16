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
