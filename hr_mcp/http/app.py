from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from hr_mcp.mcp.jsonrpc import JsonRpcError, JsonRpcHandler
from hr_mcp.services.config_center import ConfigCenter
from hr_mcp.services.identity_service import IdentityError, IdentityService
from hr_mcp.services.runtime import RuntimeContainer, build_runtime


class HrMcpHttpApp:
    DEBUG_TOOL_ROLES = {"HR_ADMIN", "MCP_DEBUG"}

    def __init__(self, runtime: RuntimeContainer, identity_service: IdentityService | None = None):
        self.runtime = runtime
        self.identity_service = identity_service or IdentityService(runtime.config)
        self.jsonrpc = JsonRpcHandler(runtime.router)

    def handle_request(self, method: str, path: str, headers: dict[str, str] | None, body: bytes | str | None) -> tuple[int, dict[str, Any]]:
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
        if method == "GET" and route == "/mcp/tools":
            identity_result = self._identity(headers)
            if isinstance(identity_result, tuple):
                return identity_result
            if identity_result.role not in self.DEBUG_TOOL_ROLES:
                return 403, {"error": "forbidden"}
            return 200, {"tools": self.runtime.router.list_tools()}
        if method == "POST" and route == "/mcp":
            identity_result = self._identity(headers)
            if isinstance(identity_result, tuple):
                return identity_result
            payload = self._json_body(body)
            if payload is None:
                return 400, self._jsonrpc_error(None, JsonRpcError.PARSE_ERROR, "Invalid JSON body")
            return 200, self.jsonrpc.handle(payload, identity_result)
        if method == "POST" and route == "/internal/audit/query":
            identity_result = self._identity(headers)
            if isinstance(identity_result, tuple):
                return identity_result
            if identity_result.role not in self.DEBUG_TOOL_ROLES:
                return 403, {"error": "forbidden"}
            params = self._json_body(body) or {}
            query = parse_qs(parsed.query)
            try:
                limit = int(params.get("limit") or (query.get("limit", [100])[0]) or 100)
            except (TypeError, ValueError):
                return 400, {"error": "invalid_limit"}
            return 200, {"records": self.runtime.read_audit_records(limit=limit)}
        return 404, {"error": "not_found"}

    def _identity(self, headers: dict[str, str]):
        try:
            return self.identity_service.from_headers(headers)
        except IdentityError:
            return 401, {"error": "unauthorized_gateway"}

    def _json_body(self, body: bytes | str | None) -> dict[str, Any] | None:
        if body is None or body == b"" or body == "":
            return {}
        try:
            raw = body.decode("utf-8") if isinstance(body, bytes) else body
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    def _jsonrpc_error(self, request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def create_app(config: ConfigCenter | None = None) -> HrMcpHttpApp:
    runtime = build_runtime(config or ConfigCenter())
    return HrMcpHttpApp(runtime)


class _RequestHandler(BaseHTTPRequestHandler):
    server_version = "HrMcpHttp/0.1"

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _dispatch(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length else b""
        app: HrMcpHttpApp = self.server.app  # type: ignore[attr-defined]
        status, payload = app.handle_request(self.command, self.path, dict(self.headers.items()), body)
        response = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def serve(config: ConfigCenter | None = None) -> None:
    config = config or ConfigCenter()
    app = create_app(config)
    server = ThreadingHTTPServer((config.host, config.port), _RequestHandler)
    server.app = app  # type: ignore[attr-defined]
    print(f"HR MCP/API listening on http://{config.host}:{config.port}")
    server.serve_forever()
