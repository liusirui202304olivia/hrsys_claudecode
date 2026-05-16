from collections import Counter
from typing import Any

from hr_mcp.models.context import IdentityContext


class TalentAnalysisService:
    MAX_ANALYSIS_ROWS = 10_000

    def __init__(self, repository, safe_view_service=None):
        self.repository = repository
        self.safe_view_service = safe_view_service

    def analyze_talent_pool(
        self,
        analysis_target: str,
        policy_id: str,
        filters: dict,
        dimensions: list[str],
        sample_limit: int,
        identity: IdentityContext | None = None,
    ) -> dict:
        filters = filters or {}
        dimensions = dimensions or []
        scoped_records = self._scoped_records(filters, identity)
        dimension_analysis: dict = {}
        if "position_name" in dimensions or "position" in dimensions:
            dimension_analysis["position_distribution"] = self._distribution(scoped_records, "position_name")
        if "status" in dimensions:
            dimension_analysis["status_distribution"] = self._distribution(scoped_records, "status")
        if "source_name" in dimensions or "source" in dimensions:
            dimension_analysis["source_distribution"] = self._distribution(scoped_records, "source_name")
        samples = self._safe_samples(scoped_records[: max(0, min(int(sample_limit or 0), 30))], identity)
        return {
            "analysis_target": analysis_target,
            "policy_id": policy_id,
            "summary_stats": {"total_candidates": len(scoped_records)},
            "dimension_analysis": dimension_analysis,
            "observations": self._observations(dimension_analysis),
            "sample_candidates": samples,
        }

    def _scoped_records(self, filters: dict[str, Any], identity: IdentityContext | None) -> list[dict]:
        records = self.repository.search_candidates(filters, self.MAX_ANALYSIS_ROWS)
        if identity is None:
            return records
        if identity.role == "READONLY_VIEWER":
            return records
        if self.safe_view_service:
            return self.safe_view_service.permission_service.filter_candidate_records(records, identity)
        return records

    def _safe_samples(self, raw_samples: list[dict], identity: IdentityContext | None) -> list[dict]:
        if identity is not None and identity.role == "READONLY_VIEWER":
            return []
        if self.safe_view_service and identity is not None:
            return self.safe_view_service.project_records("hr_candidate", raw_samples, None, identity)
        blocked_fields = {"mobile", "email", "phone", "username"}
        return [{key: value for key, value in row.items() if key not in blocked_fields} for row in raw_samples]

    def _distribution(self, records: list[dict], field_name: str) -> list[dict]:
        counts = Counter((row.get(field_name) or "UNKNOWN") for row in records)
        return [
            {field_name: key, "count": count}
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))
        ]

    def _observations(self, dimension_analysis: dict) -> list[str]:
        observations: list[str] = []
        if dimension_analysis.get("position_distribution"):
            top = dimension_analysis["position_distribution"][0]
            observations.append(f"候选人主要集中在 {top.get('position_name')}，数量 {top.get('count')}")
        if dimension_analysis.get("status_distribution"):
            observations.append("候选人状态分布已生成，可用于判断流程积压")
        return observations or ["候选人池数据已生成，建议结合岗位标准进一步筛选"]
