"""身份解析服务。

该文件把 API Gateway 透传的 header 转换为 `IdentityContext`，并支持本地开发 mock identity。
当配置 Gateway shared secret 时，它会要求请求携带匹配的 `X-Gateway-Secret`，避免客户端直连伪造角色。
身份服务不判断字段可见性，只为权限服务、审计和工具路由提供可信上下文。
"""

from hr_mcp.models.context import IdentityContext
from hr_mcp.services.config_center import ConfigCenter


class IdentityError(PermissionError):
    pass


class IdentityService:
    def __init__(self, config: ConfigCenter | None = None):
        self.config = config or ConfigCenter()

    def from_headers(self, headers: dict[str, str] | None) -> IdentityContext:
        headers = headers or {}
        normalized = {key.lower(): value for key, value in headers.items()}
        if not normalized and self.config.get_bool("HR_MOCK_IDENTITY_ENABLED", False):
            return IdentityContext(
                user_id=self.config.get_int("HR_MOCK_USER_ID"),
                user_name=self.config.get("HR_MOCK_USER_NAME"),
                role=self.config.get("HR_MOCK_USER_ROLE", "READONLY_VIEWER") or "READONLY_VIEWER",
                department_id=self.config.get_int("HR_MOCK_DEPARTMENT_ID"),
                client_id=self.config.get("HR_MOCK_CLIENT_ID", "local-dev"),
                request_id="mock-request",
                trace_id="mock-trace",
                access_reason=self.config.get("HR_MOCK_ACCESS_REASON"),
                mock_gateway_identity=True,
            )
        self._assert_trusted_gateway(normalized)
        return IdentityContext(
            user_id=self._int_or_none(normalized.get("x-user-id")),
            user_name=normalized.get("x-user-name"),
            role=normalized.get("x-user-role") or "READONLY_VIEWER",
            department_id=self._int_or_none(normalized.get("x-department-id")),
            client_id=normalized.get("x-client-id"),
            request_id=normalized.get("x-request-id"),
            trace_id=normalized.get("x-trace-id"),
            access_reason=normalized.get("x-access-reason"),
            mock_gateway_identity=False,
        )

    def _assert_trusted_gateway(self, normalized_headers: dict[str, str]) -> None:
        expected = self.config.gateway_shared_secret
        if expected and normalized_headers.get("x-gateway-secret") != expected:
            raise IdentityError("Untrusted Gateway headers")

    def _int_or_none(self, value: str | None) -> int | None:
        if value is None or value == "":
            return None
        return int(value)
