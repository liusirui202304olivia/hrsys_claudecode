"""领域模型包。

该包放置跨层共享的数据结构，例如 Gateway 身份上下文和后续可扩展的请求/响应模型。
模型文件应保持轻量，只表达数据形态，不写业务流程和外部 I/O。
服务、HTTP 和 repository 层通过这些模型共享明确的类型边界。
"""

from hr_mcp.models.context import IdentityContext
