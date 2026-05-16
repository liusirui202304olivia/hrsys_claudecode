"""审计追踪服务。

该文件负责把 MCP 工具调用、用户身份、候选人范围、字段范围和访问理由写入本地 JSONL 审计日志。
审计入参会清洗联系方式等敏感字段，避免日志成为绕过字段策略的泄露通道。
该服务不决定工具权限，只记录已经经过路由和服务层处理的调用事实。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hr_mcp.models.context import IdentityContext


SENSITIVE_AUDIT_FIELDS = {"mobile", "email", "phone", "username"}


class AuditTraceService:
    def __init__(self, audit_path: str | Path):
        self.audit_path = Path(audit_path)

    def record_tool_call(self, tool_name: str, arguments: dict, result_summary: str, identity: IdentityContext, candidate_ids: list | None = None, fields: list | None = None) -> dict:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "request_id": identity.request_id,
            "trace_id": identity.trace_id,
            "user_id": identity.user_id,
            "role": identity.role,
            "department_id": identity.department_id,
            "client_id": identity.client_id,
            "tool_name": tool_name,
            "arguments": self._sanitize(arguments),
            "candidate_ids": candidate_ids or [],
            "fields": [field for field in (fields or []) if field not in SENSITIVE_AUDIT_FIELDS],
            "access_reason": identity.access_reason,
            "mock_gateway_identity": identity.mock_gateway_identity,
            "result_summary": result_summary,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def record_tool_failure(self, tool_name: str, arguments: dict, identity: IdentityContext, error_type: str, error_message: str, fields: list | None = None) -> dict:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "request_id": identity.request_id,
            "trace_id": identity.trace_id,
            "user_id": identity.user_id,
            "role": identity.role,
            "department_id": identity.department_id,
            "client_id": identity.client_id,
            "tool_name": tool_name,
            "arguments": self._sanitize(arguments),
            "candidate_ids": [],
            "fields": [field for field in (fields or []) if field not in SENSITIVE_AUDIT_FIELDS],
            "access_reason": identity.access_reason,
            "mock_gateway_identity": identity.mock_gateway_identity,
            "result_summary": "failed",
            "error_type": error_type,
            "error_message": error_message,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._sanitize(item) for key, item in value.items() if key not in SENSITIVE_AUDIT_FIELDS}
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        return value
