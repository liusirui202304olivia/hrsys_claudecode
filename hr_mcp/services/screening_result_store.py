"""推荐结果存储服务。

该文件把 Claude Code Agent 产出的筛选任务 ID、标准名称或路径、推荐候选人 JSON 和操作者身份写入本地 JSONL。
存储前会移除联系方式和用户名等敏感字段，避免推荐结果落盘时绕过字段权限。
工具级授权由 ToolRouter 控制；本服务只保存 Agent 已经生成的推荐结果，不生成推荐理由或风险点。
"""

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

    def save_screening_result(
        self,
        task_id: str,
        standard_ref: str,
        recommended_candidates: list[dict],
        identity: IdentityContext,
    ) -> dict:
        self.result_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "task_id": task_id,
            "standard_ref": standard_ref,
            "recommended_candidates": [self._sanitize_candidate(candidate) for candidate in recommended_candidates],
            "user_id": identity.user_id,
            "role": identity.role,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.result_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def _sanitize_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        allowed = {"candidate_id", "recommend_reason", "risk_points"}
        sanitized = {key: value for key, value in dict(candidate or {}).items() if key in allowed and key not in SENSITIVE_RESULT_FIELDS}
        sanitized.setdefault("risk_points", [])
        return sanitized
