"""MCP 协议适配包。

该包用于放置 MCP over HTTP 相关的 JSON-RPC 编解码与协议错误处理。
协议层只理解 MCP 方法和 JSON-RPC 响应格式，不承担工具业务实现。
业务工具的注册和分发由 `services.tool_registry` 与 `services.tool_router` 管理。
"""
