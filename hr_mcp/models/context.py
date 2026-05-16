"""身份上下文模型。

该文件定义从 Gateway header 或本地 mock 配置构造出的 `IdentityContext`。
上下文包含用户 ID、姓名、角色、部门、客户端、链路追踪、访问理由和 mock 标记。
字段权限、行级权限、审计和工具调用都依赖该模型判断当前请求的安全范围。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IdentityContext:
    user_id: int | None = None
    user_name: str | None = None
    role: str = "READONLY_VIEWER"
    department_id: int | None = None
    client_id: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    access_reason: str | None = None
    mock_gateway_identity: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
