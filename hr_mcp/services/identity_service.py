"""身份解析服务。

该文件把 HTTP `Authorization: Bearer <token>` 转换为 `IdentityContext`。
token 到用户、角色和部门的映射只从服务端配置文件读取，客户端传入的 `X-User-*` header 不被信任。
身份服务不判断字段可见性，只为权限服务、审计和工具路由提供可信上下文。
"""

import json
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from hr_mcp.models.context import IdentityContext
from hr_mcp.services.config_center import ConfigCenter


class IdentityError(PermissionError):
    pass


class IdentityService:
    def __init__(self, config=None):
        # type: (Optional[ConfigCenter]) -> None
        self.config = config or ConfigCenter()
        self._token_cache = None  # type: Optional[Dict[str, Dict[str, object]]]

    def from_headers(self, headers):
        # type: (Optional[Dict[str, str]]) -> IdentityContext
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
        token = self._bearer_token(normalized)
        token_record = self._token_records().get(token)
        if not token_record:
            raise IdentityError("Invalid or missing Bearer token")
        return IdentityContext(
            user_id=self._int_or_none(token_record.get("user_id")),
            user_name=self._str_or_none(token_record.get("user_name")),
            role=self._str_or_none(token_record.get("role")) or "READONLY_VIEWER",
            department_id=self._int_or_none(token_record.get("department_id")),
            client_id=normalized.get("x-client-id"),
            request_id=normalized.get("x-request-id"),
            trace_id=normalized.get("x-trace-id"),
            access_reason=normalized.get("x-access-reason"),
            mock_gateway_identity=False,
            extra={"auth_mode": "bearer_token"},
        )

    def with_access_reason(self, identity, access_reason):
        # type: (IdentityContext, Optional[str]) -> IdentityContext
        if not access_reason or identity.access_reason:
            return identity
        return IdentityContext(
            user_id=identity.user_id,
            user_name=identity.user_name,
            role=identity.role,
            department_id=identity.department_id,
            client_id=identity.client_id,
            request_id=identity.request_id,
            trace_id=identity.trace_id,
            access_reason=access_reason,
            mock_gateway_identity=identity.mock_gateway_identity,
            extra=dict(identity.extra),
        )

    def _token_records(self):
        # type: () -> Dict[str, Dict[str, object]]
        if self._token_cache is not None:
            return self._token_cache
        path = self.config.auth_tokens_path
        if not path.exists():
            self._token_cache = {}
            return self._token_cache
        data = json.loads(path.read_text(encoding="utf-8"))
        self._token_cache = data.get("tokens", {})
        return self._token_cache

    def _bearer_token(self, normalized_headers):
        # type: (Dict[str, str]) -> str
        value = normalized_headers.get("authorization") or ""
        prefix = "Bearer "
        if not value.startswith(prefix):
            raise IdentityError("Missing Authorization Bearer token")
        token = value[len(prefix):].strip()
        if not token:
            raise IdentityError("Missing Authorization Bearer token")
        return token

    def _int_or_none(self, value):
        # type: (object) -> Optional[int]
        if value is None or value == "":
            return None
        return int(value)

    def _str_or_none(self, value):
        # type: (object) -> Optional[str]
        if value is None:
            return None
        return str(value)
