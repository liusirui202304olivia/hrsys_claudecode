"""身份上下文模型。

该文件定义由中心化 HTTP-MCP 服务鉴权后构造出的 `IdentityContext`。
上下文包含用户 ID、姓名、角色、部门、客户端、链路追踪、访问理由和 mock 标记。
字段权限、行级权限、审计和工具调用都依赖该模型判断当前请求的安全范围。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union


@dataclass(frozen=True)
class IdentityContext:
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    role: str = "READONLY_VIEWER"
    department_id: Optional[int] = None
    client_id: Optional[str] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    access_reason: Optional[str] = None
    mock_gateway_identity: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)
