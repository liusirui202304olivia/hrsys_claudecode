"""MCP over HTTP JSON-RPC 编解码器。

该文件负责识别 `tools/list` 与 `tools/call` 请求，校验 JSON-RPC 基本结构，并把调用交给 ToolRouter。
它将未知方法、未知工具、参数类型错误和内部异常映射为稳定的 JSON-RPC error code。
协议边界在这里终止；候选人权限、字段策略、事实查询和结果保存都由安全数据服务层完成。
"""

from __future__ import annotations

from typing import Any

from hr_mcp.models.context import IdentityContext
from hr_mcp.security.field_policy import FieldAccessError
from hr_mcp.services.tool_router import InvalidToolArgumentsError, UnknownToolError


class JsonRpcError:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    FORBIDDEN = -32003


class InvalidParamsError(ValueError):
    pass


class JsonRpcHandler:
    def __init__(self, router):
        self.router = router

    def handle(self, payload: dict[str, Any], identity: IdentityContext) -> dict[str, Any]:
        request_id = payload.get("id") if isinstance(payload, dict) else None
        try:
            if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
                raise ValueError("Invalid JSON-RPC request")
            method = payload.get("method")
            params = payload.get("params", {})
            if params is None:
                params = {}
            if method == "tools/list":
                if not isinstance(params, dict):
                    raise InvalidParamsError("tools/list params must be an object")
                result = {"tools": self.router.list_tools()}
            elif method == "tools/call":
                result = self._handle_tool_call(params, identity)
            else:
                raise UnknownToolError(f"Unknown JSON-RPC method: {method}")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except UnknownToolError as exc:
            return self._error(request_id, JsonRpcError.METHOD_NOT_FOUND, str(exc))
        except (InvalidParamsError, InvalidToolArgumentsError, TypeError) as exc:
            return self._error(request_id, JsonRpcError.INVALID_PARAMS, str(exc))
        except (PermissionError, FieldAccessError) as exc:
            return self._error(request_id, JsonRpcError.FORBIDDEN, str(exc))
        except ValueError as exc:
            return self._error(request_id, JsonRpcError.INVALID_REQUEST, str(exc))
        except Exception as exc:  # pragma: no cover - defensive protocol boundary
            return self._error(request_id, JsonRpcError.INTERNAL_ERROR, str(exc))

    def _handle_tool_call(self, params: Any, identity: IdentityContext) -> dict[str, Any]:
        if not isinstance(params, dict):
            raise InvalidParamsError("tools/call params must be an object")
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            exc = InvalidParamsError("tools/call name must be a non-empty string")
            self._record_failed_tool_call("<invalid>", {}, identity, exc)
            raise exc
        arguments = params.get("arguments", {})
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            exc = InvalidParamsError("tools/call arguments must be an object")
            self._record_failed_tool_call(tool_name, {}, identity, exc)
            raise exc
        return self.router.call_tool(tool_name, arguments, identity)

    def _error(self, request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def _record_failed_tool_call(self, tool_name: str, arguments: dict[str, Any], identity: IdentityContext, exc: Exception) -> None:
        recorder = getattr(self.router, "record_failed_call", None)
        if recorder:
            recorder(tool_name, arguments, identity, exc)
