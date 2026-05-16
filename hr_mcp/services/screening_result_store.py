from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hr_mcp.models.context import IdentityContext


SENSITIVE_RESULT_FIELDS = {"mobile", "email", "phone", "username"}


class ScreeningResultStore:
    def __init__(self, result_path: str | Path):
        self.result_path = Path(result_path)

    def save_screening_result(self, screening_task_id: str, policy_id: str, recommended_candidates: list[dict], summary: str, identity: IdentityContext) -> dict:
        self.result_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "screening_task_id": screening_task_id,
            "policy_id": policy_id,
            "recommended_candidates": [self._sanitize_candidate(candidate) for candidate in recommended_candidates],
            "summary": summary,
            "user_id": identity.user_id,
            "role": identity.role,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.result_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def _sanitize_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in dict(candidate or {}).items() if key not in SENSITIVE_RESULT_FIELDS}
