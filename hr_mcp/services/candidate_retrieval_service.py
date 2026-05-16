from hr_mcp.models.context import IdentityContext
from hr_mcp.services.candidate_safe_view_service import CandidateSafeViewService


class CandidateRetrievalService:
    DEFAULT_LIMIT = 50
    MAX_SEARCH_LIMIT = 300
    MAX_DETAIL_BATCH = 50

    def __init__(self, repository, safe_view_service: CandidateSafeViewService):
        self.repository = repository
        self.safe_view_service = safe_view_service

    def search_safe_profiles(self, filters: dict, return_fields: list[str] | None, limit: int, identity: IdentityContext) -> list[dict]:
        effective_limit = max(0, min(int(limit or self.DEFAULT_LIMIT), self.MAX_SEARCH_LIMIT))
        records = self.repository.search_candidates(filters or {}, effective_limit)
        return self.safe_view_service.project_records("hr_candidate", records, return_fields, identity)

    def get_safe_detail_batch(self, candidate_ids: list[int | str], return_fields: list[str] | None, identity: IdentityContext) -> dict:
        requested = list(candidate_ids or [])[: self.MAX_DETAIL_BATCH]
        records = self.repository.get_candidates_by_ids(requested)
        return {
            "candidate_ids_requested": requested,
            "limit_applied": self.MAX_DETAIL_BATCH,
            "candidates": self.safe_view_service.project_records("hr_candidate", records, return_fields, identity),
        }
