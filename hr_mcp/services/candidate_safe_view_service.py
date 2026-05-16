"""候选人安全画像服务。

该文件负责执行字段白名单校验、行级权限过滤和记录投影，是原始候选人数据进入 Agent 上下文前的安全边界。
字段校验会先于行过滤发生，避免低权限请求高权限字段时因空结果绕过校验。
所有候选人明细输出都应通过该服务，而不是由工具或 repository 直接返回。
"""

from hr_mcp.models.context import IdentityContext
from hr_mcp.security.field_policy import FieldPolicy
from hr_mcp.services.permission_service import PermissionService


class CandidateSafeViewService:
    def __init__(self, field_policy: FieldPolicy, permission_service: PermissionService):
        self.field_policy = field_policy
        self.permission_service = permission_service

    def allowed_fields(self, table: str, requested_fields: list[str] | None, identity: IdentityContext) -> list[str]:
        return self.field_policy.allowed_fields(
            table=table,
            requested_fields=requested_fields,
            role=identity.role,
            access_reason=identity.access_reason,
        )

    def project_record(self, table: str, record: dict, requested_fields: list[str] | None, identity: IdentityContext) -> dict:
        allowed = self.allowed_fields(table, requested_fields, identity)
        return self._project_with_allowed(record, allowed)

    def project_records(self, table: str, records: list[dict], requested_fields: list[str] | None, identity: IdentityContext) -> list[dict]:
        allowed = self.allowed_fields(table, requested_fields, identity)
        scoped = self.permission_service.filter_candidate_records(records, identity) if table == "hr_candidate" else records
        return [self._project_with_allowed(row, allowed) for row in scoped]

    def _project_with_allowed(self, record: dict, allowed: list[str]) -> dict:
        return {field_name: record.get(field_name) for field_name in allowed if field_name in record}
