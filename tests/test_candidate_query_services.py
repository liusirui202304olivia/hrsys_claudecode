"""候选人召回与人才库查询服务测试。

该文件验证候选人明细必须经过安全投影、高权限字段对普通角色拒绝、批量详情限制和 READONLY 明细禁止访问。
同时覆盖聚合事实查询的无联系方式输出，以及招聘者等角色的聚合范围收敛。
这些测试保护 CandidateRetrievalService、TalentPoolQueryService 和 PermissionService 的核心安全边界。
"""

from hr_mcp.models.context import IdentityContext
import pytest

from hr_mcp.security.field_policy import FieldAccessError, FieldPolicy
from hr_mcp.services.candidate_retrieval_service import CandidateRetrievalService
from hr_mcp.services.candidate_safe_view_service import CandidateSafeViewService
from hr_mcp.services.permission_service import PermissionService
from hr_mcp.services.talent_pool_query_service import TalentPoolQueryService


class FakeRepository:
    def __init__(self):
        self.records = [
            {
                "id": 1,
                "candidate_id": 1,
                "name": "张三",
                "gender": "MALE",
                "mobile": "13800000000",
                "email": "z@example.com",
                "status": "SCREEN_PROCESS",
                "hr_id": 2,
                "work_years": 5,
                "position_name": "芯片建模工程师",
                "skills": '["C++", "gem5"]',
            },
            {
                "id": 2,
                "candidate_id": 2,
                "name": "李四",
                "gender": "FEMALE",
                "mobile": "13900000000",
                "email": "l@example.com",
                "status": "REJECTED",
                "hr_id": 3,
                "work_years": 1,
                "position_name": "应用软件开发工程师",
                "skills": '["Java"]',
            },
        ]

    def search_candidates(self, filters, limit):
        return self.records[:limit]

    def get_candidates_by_ids(self, candidate_ids):
        ids = {int(candidate_id) for candidate_id in candidate_ids}
        return [row for row in self.records if row["id"] in ids]

    def count_candidates(self, filters):
        return len(self.records)

    def position_distribution(self, filters):
        return [
            {"position_name": "芯片建模工程师", "count": 1},
            {"position_name": "应用软件开发工程师", "count": 1},
        ]

    def status_distribution(self, filters):
        return [{"status": "SCREEN_PROCESS", "count": 1}, {"status": "REJECTED", "count": 1}]

    def source_distribution(self, filters):
        return [{"source_name": "历史导入", "count": 2}]


def make_services():
    permission = PermissionService()
    safe_view = CandidateSafeViewService(FieldPolicy(), permission)
    repo = FakeRepository()
    retrieval = CandidateRetrievalService(repo, safe_view)
    query = TalentPoolQueryService(repo, safe_view)
    return retrieval, query


def test_search_profiles_returns_only_safe_fields_for_recruiter_scope():
    retrieval, _ = make_services()
    identity = IdentityContext(user_id=2, role="RECRUITER")

    rows = retrieval.search_safe_profiles(
        filters={},
        return_fields=["name", "gender", "status"],
        limit=10,
        identity=identity,
    )

    assert rows == [{"name": "张三", "gender": "MALE", "status": "SCREEN_PROCESS"}]


def test_search_profiles_rejects_privileged_fields_for_non_privileged_role():
    retrieval, _ = make_services()
    identity = IdentityContext(user_id=2, role="RECRUITER")

    with pytest.raises(FieldAccessError):
        retrieval.search_safe_profiles(
            filters={},
            return_fields=["name", "mobile"],
            limit=10,
            identity=identity,
        )


def test_detail_batch_is_limited_to_50_candidates():
    retrieval, _ = make_services()
    identity = IdentityContext(user_id=1, role="HR_ADMIN")

    result = retrieval.get_safe_detail_batch(
        candidate_ids=list(range(100)),
        return_fields=["name"],
        identity=identity,
    )

    assert len(result["candidate_ids_requested"]) == 50
    assert result["limit_applied"] == 50


def test_query_facts_returns_aggregate_without_contact_fields():
    _, query = make_services()
    identity = IdentityContext(user_id=1, role="READONLY_VIEWER")

    result = query.query_facts(
        metrics=["count"],
        filters={},
        group_by=["position_name", "status", "source_name"],
        identity=identity,
    )

    assert result["count"] == 2
    assert "mobile" not in str(result)
    assert "email" not in str(result)
    assert {row["position_name"] for row in result["position_distribution"]} == {"芯片建模工程师", "应用软件开发工程师"}




def test_readonly_viewer_cannot_retrieve_candidate_profiles():
    retrieval, _ = make_services()
    identity = IdentityContext(user_id=9, role="READONLY_VIEWER")

    rows = retrieval.search_safe_profiles(
        filters={},
        return_fields=["name", "gender", "status"],
        limit=10,
        identity=identity,
    )

    assert rows == []


def test_query_facts_applies_recruiter_scope_to_aggregates():
    _, query = make_services()
    identity = IdentityContext(user_id=2, role="RECRUITER")

    result = query.query_facts(
        metrics=["count"],
        filters={},
        group_by=["position_name", "status"],
        identity=identity,
    )

    assert result["count"] == 1
    assert result["position_distribution"] == [{"position_name": "芯片建模工程师", "count": 1}]
    assert result["status_distribution"] == [{"status": "SCREEN_PROCESS", "count": 1}]
