"""FastAPI HTTP MCP 应用入口。

该文件提供 `/healthz`、`/readyz`、`/mcp`、`/mcp/tools` 和内部审计查询接口。
它负责 HTTP JSON 编解码、Bearer token 鉴权、IP 白名单、限流、请求体大小限制和 FastAPI 路由绑定。
本层不直接访问 SQL dump 或 MySQL，也不实现候选人筛选、字段白名单或招聘分析逻辑。
"""

import json
import time
from datetime import date, datetime
from decimal import Decimal
from ipaddress import ip_address, ip_network
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hr_mcp.mcp.jsonrpc import JsonRpcError, JsonRpcHandler
from hr_mcp.models.context import IdentityContext
from hr_mcp.services.config_center import ConfigCenter
from hr_mcp.services.identity_service import IdentityError, IdentityService
from hr_mcp.services.runtime import RuntimeContainer, build_runtime


class HrMcpHttpApp:
    DEBUG_TOOL_ROLES = {"HR_ADMIN", "MCP_DEBUG"}

    def __init__(self, runtime, identity_service=None):
        # type: (RuntimeContainer, Optional[IdentityService]) -> None
        self.runtime = runtime
        self.identity_service = identity_service or IdentityService(runtime.config)
        self.jsonrpc = JsonRpcHandler(runtime.router)
        self._rate_windows = {}  # type: Dict[str, Tuple[int, int]]

    def handle_request(self, method, path, headers=None, body=None, client_ip=None):
        # type: (str, str, Optional[Dict[str, str]], Optional[object], Optional[str]) -> Tuple[int, Dict[str, Any]]
        parsed = urlparse(path)
        route = parsed.path
        method = method.upper()
        headers = headers or {}

        if method == "GET" and route == "/healthz":
            return 200, {"status": "ok"}
        if method == "GET" and route == "/readyz":
            checks = self.runtime.ready_checks()
            status = 200 if all(checks.values()) else 503
            return status, {"status": "ready" if status == 200 else "not_ready", "checks": checks}
        if self._body_too_large(body):
            return self._http_failure(method, route, headers, client_ip, 413, "request_too_large", "Request body exceeds configured max size")
        if not self._ip_allowed(headers, client_ip):
            return self._http_failure(method, route, headers, client_ip, 403, "ip_forbidden", "Client IP is not in allowlist")

        if method == "GET" and route == "/mcp/tools":
            identity_result = self._identity(headers, route, method, client_ip=client_ip)
            if isinstance(identity_result, tuple):
                return identity_result
            if self._rate_limited(identity_result):
                return self._http_failure(method, route, headers, client_ip, 429, "rate_limited", "User exceeded rate limit", identity_result)
            if identity_result.role not in self.DEBUG_TOOL_ROLES:
                return self._http_failure(method, route, headers, client_ip, 403, "forbidden", "Role cannot list tools", identity_result)
            return 200, {"tools": self.runtime.router.list_tools()}

        if method == "POST" and route == "/mcp":
            payload = self._json_body(body)
            if payload is None:
                return 400, self._jsonrpc_error(None, JsonRpcError.PARSE_ERROR, "Invalid JSON body")
            identity_result = self._identity(headers, route, method, payload, client_ip=client_ip)
            if isinstance(identity_result, tuple):
                return identity_result
            if self._rate_limited(identity_result):
                return self._http_failure(method, route, headers, client_ip, 429, "rate_limited", "User exceeded rate limit", identity_result)
            return 200, self.jsonrpc.handle(payload, identity_result)

        if method == "POST" and route == "/internal/audit/query":
            identity_result = self._identity(headers, route, method, client_ip=client_ip)
            if isinstance(identity_result, tuple):
                return identity_result
            if self._rate_limited(identity_result):
                return self._http_failure(method, route, headers, client_ip, 429, "rate_limited", "User exceeded rate limit", identity_result)
            if identity_result.role not in self.DEBUG_TOOL_ROLES:
                return self._http_failure(method, route, headers, client_ip, 403, "forbidden", "Role cannot query audit records", identity_result)
            params = self._json_body(body) or {}
            query = parse_qs(parsed.query)
            try:
                limit = int(params.get("limit") or (query.get("limit", [100])[0]) or 100)
            except (TypeError, ValueError):
                return 400, {"error": "invalid_limit"}
            return 200, {"records": self.runtime.read_audit_records(limit=limit)}

        return 404, {"error": "not_found"}

    def as_fastapi(self):
        # type: () -> FastAPI
        api = FastAPI(title="HR MCP API", version="0.1.0")
        owner = self

        @api.get("/healthz")
        async def healthz():
            status, payload = owner.handle_request("GET", "/healthz", {}, b"")
            return owner._json_response(payload, status)

        @api.get("/readyz")
        async def readyz():
            status, payload = owner.handle_request("GET", "/readyz", {}, b"")
            return owner._json_response(payload, status)

        @api.get("/mcp/tools")
        async def tools(request: Request):
            status, payload = owner.handle_request("GET", "/mcp/tools", dict(request.headers.items()), b"", owner._request_client_ip(request))
            return owner._json_response(payload, status)

        @api.post("/mcp")
        async def mcp(request: Request):
            body = await request.body()
            status, payload = owner.handle_request("POST", "/mcp", dict(request.headers.items()), body, owner._request_client_ip(request))
            return owner._json_response(payload, status)

        @api.post("/internal/audit/query")
        async def audit_query(request: Request):
            body = await request.body()
            status, payload = owner.handle_request(
                "POST",
                str(request.url.path) + ("?" + request.url.query if request.url.query else ""),
                dict(request.headers.items()),
                body,
                owner._request_client_ip(request),
            )
            return owner._json_response(payload, status)

        return api

    def _json_response(self, payload, status):
        # type: (Dict[str, Any], int) -> JSONResponse
        return JSONResponse(self._json_ready(payload), status_code=status)

    def _json_ready(self, value):
        # type: (Any) -> Any
        if isinstance(value, dict):
            return {str(key): self._json_ready(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_ready(item) for item in value]
        if isinstance(value, datetime):
            return value.isoformat(sep=" ")
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError:
                return value.decode("utf-8", errors="replace")
        return value

    def _identity(self, headers, route="/mcp", method="POST", payload=None, client_ip=None):
        # type: (Dict[str, str], str, str, Optional[Dict[str, Any]], Optional[str]) -> object
        try:
            identity = self.identity_service.from_headers(headers)
            access_reason = self._payload_access_reason(payload)
            return self.identity_service.with_access_reason(identity, access_reason)
        except IdentityError:
            return self._http_failure(method, route, headers, client_ip, 401, "unauthorized", "Missing or invalid bearer token")

    def _payload_access_reason(self, payload):
        # type: (Optional[Dict[str, Any]]) -> Optional[str]
        if not isinstance(payload, dict):
            return None
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            return None
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return None
        value = arguments.get("access_reason")
        return value if isinstance(value, str) and value.strip() else None

    def _json_body(self, body):
        # type: (Optional[object]) -> Optional[Dict[str, Any]]
        if body is None or body == b"" or body == "":
            return {}
        try:
            raw = body.decode("utf-8") if isinstance(body, bytes) else body
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except (TypeError, ValueError):
            return None

    def _jsonrpc_error(self, request_id, code, message):
        # type: (Any, int, str) -> Dict[str, Any]
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def _body_too_large(self, body):
        # type: (Optional[object]) -> bool
        if body is None:
            return False
        if isinstance(body, bytes):
            size = len(body)
        else:
            size = len(str(body).encode("utf-8"))
        return size > self.runtime.config.max_request_bytes

    def _ip_allowed(self, headers, client_ip=None):
        # type: (Dict[str, str], Optional[str]) -> bool
        cidrs = self.runtime.config.allowed_ip_cidrs
        if not cidrs:
            return True
        client_ip = self._client_ip(headers, client_ip)
        try:
            ip = ip_address(client_ip)
            return any(ip in ip_network(cidr, strict=False) for cidr in cidrs)
        except ValueError:
            return False

    def _client_ip(self, headers, client_ip=None):
        # type: (Dict[str, str], Optional[str]) -> str
        if client_ip:
            return client_ip
        normalized = {key.lower(): value for key, value in headers.items()}
        forwarded = normalized.get("x-forwarded-for") or normalized.get("x-real-ip") or "127.0.0.1"
        return forwarded.split(",", 1)[0].strip()

    def _request_client_ip(self, request):
        # type: (Request) -> Optional[str]
        if request.client is None:
            return None
        return request.client.host

    def _http_failure(self, method, route, headers, client_ip, status, error_type, error_message, identity=None):
        # type: (str, str, Dict[str, str], Optional[str], int, str, str, Optional[IdentityContext]) -> Tuple[int, Dict[str, Any]]
        audit_service = getattr(self.runtime.router, "audit_service", None)
        if audit_service:
            try:
                audit_service.record_http_failure(
                    route=route,
                    method=method,
                    status_code=status,
                    error_type=error_type,
                    error_message=error_message,
                    identity=identity,
                    request_id=self._header_value(headers, "x-request-id"),
                    remote_addr=self._client_ip(headers, client_ip),
                )
            except Exception:
                pass
        return status, {"error": error_type}

    def _header_value(self, headers, key):
        # type: (Dict[str, str], str) -> Optional[str]
        for header_name, value in headers.items():
            if header_name.lower() == key:
                return value
        return None

    def _rate_limited(self, identity):
        # type: (IdentityContext) -> bool
        limit = self.runtime.config.rate_limit_per_minute
        if limit <= 0:
            return False
        key = str(identity.user_id or identity.user_name or "anonymous")
        minute = int(time.time() // 60)
        window_minute, count = self._rate_windows.get(key, (minute, 0))
        if window_minute != minute:
            window_minute, count = minute, 0
        count += 1
        self._rate_windows[key] = (window_minute, count)
        return count > limit


def create_app(config=None):
    # type: (Optional[ConfigCenter]) -> HrMcpHttpApp
    runtime = build_runtime(config or ConfigCenter())
    return HrMcpHttpApp(runtime)


def create_fastapi_app(config=None):
    # type: (Optional[ConfigCenter]) -> FastAPI
    return create_app(config).as_fastapi()


def serve(config=None):
    # type: (Optional[ConfigCenter]) -> None
    import uvicorn
    config = config or ConfigCenter()
    uvicorn.run(create_fastapi_app(config), host=config.host, port=config.port)
