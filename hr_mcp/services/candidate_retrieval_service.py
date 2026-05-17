"""候选人召回服务。

该文件提供候选人安全画像搜索和候选人详情批量读取能力。
它只控制单次返回给 Agent 的页大小和详情批量大小，不限制数据库参与查询的候选人总量。
Repository 负责全量匹配计数和游标分页，本服务把返回记录交给 CandidateSafeViewService 做安全投影。
该服务是 Agent 获取候选人明细的主要入口，不能绕过字段白名单或行级权限。
"""

from typing import Any, Dict, List, Optional, Set, Tuple, Union

from hr_mcp.models.context import IdentityContext
from hr_mcp.services.candidate_safe_view_service import CandidateSafeViewService


class CandidateRetrievalService:
    DEFAULT_PAGE_SIZE = 50
    MAX_SEARCH_PAGE_SIZE = 300
    MAX_DETAIL_BATCH = 50

    def __init__(self, repository, safe_view_service: CandidateSafeViewService):
        self.repository = repository
        self.safe_view_service = safe_view_service

    def search_safe_profiles(
        self,
        filters: Dict[str, Any],
        return_fields: Optional[List[str]],
        page_size: Optional[int],
        identity: IdentityContext,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        effective_page_size = self._validate_page_size(page_size)
        identity_scope = self.safe_view_service.permission_service.candidate_query_scope(identity)
        include_privileged = self.safe_view_service.requested_privileged_fields("hr_candidate", return_fields, identity)
        page = self.repository.search_candidates(
            filters or {},
            page_size=effective_page_size,
            cursor=cursor,
            include_privileged=include_privileged,
            identity_scope=identity_scope,
        )
        projected = self.safe_view_service.project_records("hr_candidate", page.get("items", []), return_fields, identity)
        return {
            "candidates": projected,
            "total_count": int(page.get("total_count") or 0),
            "has_more": bool(page.get("has_more")),
            "next_cursor": page.get("next_cursor"),
            "page_size": effective_page_size,
        }

    def get_safe_detail_batch(self, candidate_ids: List[Union[int, str]], return_fields: Optional[List[str]], identity: IdentityContext) -> Dict[str, Any]:
        requested = list(candidate_ids or [])
        if len(requested) > self.MAX_DETAIL_BATCH:
            raise ValueError("get_candidate_safe_detail_batch accepts at most 50 candidate_ids per call")
        identity_scope = self.safe_view_service.permission_service.candidate_query_scope(identity)
        include_privileged = self.safe_view_service.requested_privileged_fields("hr_candidate", return_fields, identity)
        records = self.repository.get_candidates_by_ids(
            requested,
            include_privileged=include_privileged,
            identity_scope=identity_scope,
        )
        return {
            "candidate_ids_requested": requested,
            "max_batch_size": self.MAX_DETAIL_BATCH,
            "candidates": self.safe_view_service.project_records("hr_candidate", records, return_fields, identity),
        }

    def _validate_page_size(self, page_size: Optional[int]) -> int:
        if page_size is None:
            return self.DEFAULT_PAGE_SIZE
        if isinstance(page_size, bool):
            raise ValueError("page_size must be an integer")
        try:
            value = int(page_size)
        except (TypeError, ValueError):
            raise ValueError("page_size must be an integer")
        if value < 1 or value > self.MAX_SEARCH_PAGE_SIZE:
            raise ValueError("page_size must be between 1 and 300")
        return value
