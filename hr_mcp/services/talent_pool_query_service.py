"""人才库事实查询服务。

该文件提供 count、岗位分布、状态分布和来源分布等聚合事实查询，供 Claude Code Skill 组织自然语言回答。
聚合会先按身份上下文进行范围收敛，READONLY_VIEWER 只拿聚合结果，不拿候选人明细。
该服务不返回联系方式，也不暴露自由 SQL 查询能力。
"""

from typing import Any, Dict, List, Optional, Set, Tuple, Union

from hr_mcp.models.context import IdentityContext
from hr_mcp.services.candidate_safe_view_service import CandidateSafeViewService


class TalentPoolQueryService:
    def __init__(self, repository, safe_view_service: CandidateSafeViewService):
        self.repository = repository
        self.safe_view_service = safe_view_service

    def query_facts(self, metrics: List[str], filters: Dict[str, Any], group_by: List[str], identity: IdentityContext) -> Dict[str, Any]:
        identity_scope = self.safe_view_service.permission_service.aggregate_query_scope(identity)
        result: Dict[str, Any] = {"filters_applied": filters or {}, "permission_scope": identity.role}
        metrics = metrics or ["count"]
        group_by = group_by or []
        if "count" in metrics:
            result["count"] = self.repository.count_candidates(filters or {}, identity_scope=identity_scope)
        if "position_name" in group_by or "position" in group_by:
            result["position_distribution"] = self.repository.position_distribution(filters or {}, identity_scope=identity_scope)
        if "status" in group_by:
            result["status_distribution"] = self.repository.status_distribution(filters or {}, identity_scope=identity_scope)
        if "source_name" in group_by or "source" in group_by:
            result["source_distribution"] = self.repository.source_distribution(filters or {}, identity_scope=identity_scope)
        return result
