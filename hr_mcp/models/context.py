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
