from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from hr_mcp.models.context import IdentityContext


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
            "arguments": arguments,
            "candidate_ids": candidate_ids or [],
            "fields": fields or [],
            "access_reason": identity.access_reason,
            "mock_gateway_identity": identity.mock_gateway_identity,
            "result_summary": result_summary,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
