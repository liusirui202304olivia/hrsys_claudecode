"""安全策略包。

该包集中放置字段权限、默认可见字段、高权限字段和不可见字段的定义。
安全策略是服务层对 Agent 输出做白名单校验的基础，不应分散到工具或 HTTP 代码中。
后续新增表或字段时，应优先在这里扩展策略并补充测试。
"""

from hr_mcp.security.field_policy import FieldAccessError, FieldPolicy
