from collections import Counter
from typing import Any

from hr_mcp.models.context import IdentityContext
from hr_mcp.services.candidate_safe_view_service import CandidateSafeViewService


class TalentPoolQueryService:
    MAX_AGGREGATE_ROWS = 10_000

    def __init__(self, repository, safe_view_service: CandidateSafeViewService):
        self.repository = repository
        self.safe_view_service = safe_view_service

    def query_facts(self, metrics: list[str], filters: dict, group_by: list[str], identity: IdentityContext) -> dict:
        records = self._scoped_records(filters or {}, identity)
        result: dict = {"filters_applied": filters or {}, "permission_scope": identity.role}
        metrics = metrics or ["count"]
        group_by = group_by or []
        if "count" in metrics:
            result["count"] = len(records)
        if "position_name" in group_by or "position" in group_by:
            result["position_distribution"] = self._distribution(records, "position_name")
        if "status" in group_by:
            result["status_distribution"] = self._distribution(records, "status")
        if "source_name" in group_by or "source" in group_by:
            result["source_distribution"] = self._distribution(records, "source_name")
        return result

    def _scoped_records(self, filters: dict[str, Any], identity: IdentityContext) -> list[dict]:
        records = self.repository.search_candidates(filters, self.MAX_AGGREGATE_ROWS)
        if identity.role == "READONLY_VIEWER":
            return records
        return self.safe_view_service.permission_service.filter_candidate_records(records, identity)

    def _distribution(self, records: list[dict], field_name: str) -> list[dict]:
        counts = Counter((row.get(field_name) or "UNKNOWN") for row in records)
        return [
            {field_name: key, "count": count}
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))
        ]
