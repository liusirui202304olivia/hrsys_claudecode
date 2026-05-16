from hr_mcp.models.context import IdentityContext


class TalentAnalysisService:
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
        dimension_analysis: dict = {}
        if "position_name" in dimensions or "position" in dimensions:
            dimension_analysis["position_distribution"] = self.repository.position_distribution(filters)
        if "status" in dimensions:
            dimension_analysis["status_distribution"] = self.repository.status_distribution(filters)
        if "source_name" in dimensions or "source" in dimensions:
            dimension_analysis["source_distribution"] = self.repository.source_distribution(filters)
        raw_samples = self.repository.search_candidates(filters, max(0, min(int(sample_limit or 0), 30)))
        samples = self._safe_samples(raw_samples, identity)
        return {
            "analysis_target": analysis_target,
            "policy_id": policy_id,
            "summary_stats": {"total_candidates": self.repository.count_candidates(filters)},
            "dimension_analysis": dimension_analysis,
            "observations": self._observations(dimension_analysis),
            "sample_candidates": samples,
        }

    def _safe_samples(self, raw_samples: list[dict], identity: IdentityContext | None) -> list[dict]:
        if self.safe_view_service and identity is not None:
            return self.safe_view_service.project_records("hr_candidate", raw_samples, None, identity)
        blocked_fields = {"mobile", "email", "phone", "username"}
        return [{key: value for key, value in row.items() if key not in blocked_fields} for row in raw_samples]

    def _observations(self, dimension_analysis: dict) -> list[str]:
        observations: list[str] = []
        if dimension_analysis.get("position_distribution"):
            top = dimension_analysis["position_distribution"][0]
            observations.append(f"候选人主要集中在 {top.get('position_name')}，数量 {top.get('count')}")
        if dimension_analysis.get("status_distribution"):
            observations.append("候选人状态分布已生成，可用于判断流程积压")
        return observations or ["候选人池数据已生成，建议结合岗位标准进一步筛选"]
