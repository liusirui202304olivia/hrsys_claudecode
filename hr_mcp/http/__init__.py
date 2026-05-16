"""HTTP 协议层包。

该包承载 HTTP server、健康检查、就绪检查和 MCP over HTTP 入口。
HTTP 层只处理路由、header、JSON 编解码和响应状态码，不实现招聘业务规则。
所有工具调用都应通过 JSON-RPC handler 和 ToolRouter 下发到服务层。
"""
