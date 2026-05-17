"""人才库事实查询服务。

该文件提供 count、岗位分布、状态分布和来源分布等聚合事实查询，供 Claude Code Skill 组织自然语言回答。
聚合会先按身份上下文进行范围收敛，READONLY_VIEWER 只拿聚合结果，不拿候选人明细。
该服务不返回联系方式，也不暴露自由 SQL 查询能力。
"""

from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from hr_mcp.models.context import IdentityContext
from hr_mcp.services.candidate_safe_view_service import CandidateSafeViewService


class TalentPoolQueryService:
    MAX_AGGREGATE_ROWS = 10_000

    def __init__(self, repository, safe_view_service: CandidateSafeViewService):
        self.repository = repository
        self.safe_view_service = safe_view_service

    def query_facts(self, metrics: List[str], filters: Dict[str, Any], group_by: List[str], identity: IdentityContext) -> Dict[str, Any]:
        records = self._scoped_records(filters or {}, identity)
        result: Dict[str, Any] = {"filters_applied": filters or {}, "permission_scope": identity.role}
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

    def _scoped_records(self, filters: Dict[str, Any], identity: IdentityContext) -> List[Dict[str, Any]]:
        records = self.repository.search_candidates(filters, self.MAX_AGGREGATE_ROWS)
        if identity.role == "READONLY_VIEWER":
            return records
        return self.safe_view_service.permission_service.filter_candidate_records(records, identity)

    def _distribution(self, records: List[Dict[str, Any]], field_name: str) -> List[Dict[str, Any]]:
        counts = Counter((row.get(field_name) or "UNKNOWN") for row in records)
        return [
            {field_name: key, "count": count}
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))
        ]
