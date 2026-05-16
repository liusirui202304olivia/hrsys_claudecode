"""岗位筛选标准服务。

该文件加载 `config/policies` 中的岗位 metadata，并关联 `standard_markdown` 下的 Markdown 标准内容。
它支持岗位名称和别名匹配，为 Agent 推荐和报告生成提供岗位筛选依据。
该服务只处理标准库读取和匹配，不访问候选人数据库。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ScreeningPolicyService:
    def __init__(self, policy_dir: str | Path, markdown_dir: str | Path):
        self.policy_dir = Path(policy_dir)
        self.markdown_dir = Path(markdown_dir)

    def get_policy(self, position_query: str, department_hint: str | None = None) -> dict[str, Any]:
        policies = self._load_policies()
        query = (position_query or "").lower()
        for policy in policies:
            names = [policy.get("position_name", "")] + list(policy.get("aliases") or [])
            if any(query in str(name).lower() or str(name).lower() in query for name in names):
                return self._with_markdown(policy)
        if policies:
            first = self._with_markdown(policies[0])
            first["match_warning"] = f"未精确命中 {position_query}，已返回默认标准"
            return first
        raise LookupError("No screening policies configured")

    def _load_policies(self) -> list[dict[str, Any]]:
        policies: list[dict[str, Any]] = []
        if self.policy_dir.exists():
            for path in sorted(self.policy_dir.glob("*.yml")):
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                policies.append(data)
        if policies:
            return policies
        fallback: list[dict[str, Any]] = []
        if self.markdown_dir.exists():
            for path in sorted(self.markdown_dir.glob("*.md")):
                fallback.append({
                    "policy_id": path.stem,
                    "position_name": path.stem,
                    "version": "local",
                    "markdown_file": path.name,
                    "aliases": [path.stem],
                })
        return fallback

    def _with_markdown(self, policy: dict[str, Any]) -> dict[str, Any]:
        result = dict(policy)
        markdown_file = result.get("markdown_file")
        markdown_path = self.markdown_dir / markdown_file if markdown_file else None
        result["content_markdown"] = markdown_path.read_text(encoding="utf-8") if markdown_path and markdown_path.exists() else ""
        return result
