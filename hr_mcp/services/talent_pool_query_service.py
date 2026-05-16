from hr_mcp.models.context import IdentityContext
from hr_mcp.services.candidate_safe_view_service import CandidateSafeViewService


class TalentPoolQueryService:
    def __init__(self, repository, safe_view_service: CandidateSafeViewService):
        self.repository = repository
        self.safe_view_service = safe_view_service

    def query_facts(self, metrics: list[str], filters: dict, group_by: list[str], identity: IdentityContext) -> dict:
        result: dict = {"filters_applied": filters or {}, "permission_scope": identity.role}
        metrics = metrics or ["count"]
        group_by = group_by or []
        if "count" in metrics:
            result["count"] = self.repository.count_candidates(filters or {})
        if "position_name" in group_by or "position" in group_by:
            result["position_distribution"] = self.repository.position_distribution(filters or {})
        if "status" in group_by:
            result["status_distribution"] = self.repository.status_distribution(filters or {})
        if "source_name" in group_by or "source" in group_by:
            result["source_distribution"] = self.repository.source_distribution(filters or {})
        return result
