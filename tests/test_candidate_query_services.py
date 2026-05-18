"""候选人召回与人才库查询服务测试。

该文件验证候选人明细必须经过安全投影、高权限字段对普通角色拒绝、批量详情限制和 READONLY 明细禁止访问。
同时覆盖聚合事实查询的无联系方式输出，以及业务角色默认全库安全画像可见。
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
        self.search_calls = []
        self.count_calls = []
        self.distribution_calls = []
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

    def search_candidates(self, filters, page_size, cursor=None, include_privileged=False, identity_scope=None):
        self.search_calls.append({
            "filters": filters,
            "page_size": page_size,
            "cursor": cursor,
            "include_privileged": include_privileged,
            "identity_scope": identity_scope,
        })
        rows = self._apply_scope(self.records, identity_scope)
        page = rows[:page_size]
        return {
            "items": page,
            "total_count": len(rows),
            "has_more": len(rows) > len(page),
            "next_cursor": "cursor-2" if len(rows) > len(page) else None,
        }

    def get_candidates_by_ids(self, candidate_ids, include_privileged=False, identity_scope=None):
        ids = {int(candidate_id) for candidate_id in candidate_ids}
        rows = self._apply_scope(self.records, identity_scope)
        return [row for row in rows if row["id"] in ids]

    def count_candidates(self, filters, identity_scope=None):
        self.count_calls.append({"filters": filters, "identity_scope": identity_scope})
        return len(self._apply_scope(self.records, identity_scope))

    def position_distribution(self, filters, identity_scope=None):
        self.distribution_calls.append(("position_name", identity_scope))
        return self._distribution("position_name", identity_scope)

    def status_distribution(self, filters, identity_scope=None):
        self.distribution_calls.append(("status", identity_scope))
        return self._distribution("status", identity_scope)

    def source_distribution(self, filters, identity_scope=None):
        self.distribution_calls.append(("source_name", identity_scope))
        return self._distribution("source_name", identity_scope)

    def distribution(self, dimension, filters, identity_scope=None):
        self.distribution_calls.append((dimension, identity_scope))
        return self._distribution(dimension, identity_scope)

    def _distribution(self, field_name, identity_scope):
        counts = {}
        for row in self._apply_scope(self.records, identity_scope):
            key = row.get(field_name) or "UNKNOWN"
            counts[key] = counts.get(key, 0) + 1
        return [
            {field_name: key, "count": count}
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))
        ]

    def _apply_scope(self, rows, identity_scope):
        identity_scope = identity_scope or {}
        if identity_scope.get("deny_all"):
            return []
        return list(rows)

def make_services():
    permission = PermissionService()
    safe_view = CandidateSafeViewService(FieldPolicy(), permission)
    repo = FakeRepository()
    retrieval = CandidateRetrievalService(repo, safe_view)
    query = TalentPoolQueryService(repo, safe_view)
    return retrieval, query


def test_search_profiles_returns_all_safe_profiles_for_recruiter():
    retrieval, _ = make_services()
    identity = IdentityContext(user_id=2, role="RECRUITER")

    result = retrieval.search_safe_profiles(
        filters={},
        return_fields=["candidate_id", "name", "gender", "status"],
        page_size=10,
        identity=identity,
    )

    assert result["candidates"] == [
        {"candidate_id": 1, "name": "张三", "gender": "MALE", "status": "SCREEN_PROCESS"},
        {"candidate_id": 2, "name": "李四", "gender": "FEMALE", "status": "REJECTED"},
    ]
    assert result["total_count"] == 2
    assert result["has_more"] is False
    assert result["next_cursor"] is None


def test_search_profiles_returns_page_metadata_without_limiting_total_count():
    retrieval, _ = make_services()
    identity = IdentityContext(user_id=1, role="HR_ADMIN")

    result = retrieval.search_safe_profiles(
        filters={},
        return_fields=["candidate_id", "name"],
        page_size=1,
        cursor=None,
        identity=identity,
    )

    assert result["candidates"] == [{"candidate_id": 1, "name": "张三"}]
    assert result["total_count"] == 2
    assert result["has_more"] is True
    assert result["next_cursor"] == "cursor-2"
    assert result["page_size"] == 1


def test_search_profiles_rejects_page_size_outside_policy_limit():
    retrieval, _ = make_services()
    identity = IdentityContext(user_id=1, role="HR_ADMIN")

    with pytest.raises(ValueError):
        retrieval.search_safe_profiles(
            filters={},
            return_fields=["candidate_id"],
            page_size=301,
            identity=identity,
        )


def test_search_profiles_rejects_privileged_fields_for_non_privileged_role():
    retrieval, _ = make_services()
    identity = IdentityContext(user_id=2, role="RECRUITER")

    with pytest.raises(FieldAccessError):
        retrieval.search_safe_profiles(
            filters={},
            return_fields=["name", "mobile"],
            page_size=10,
            identity=identity,
        )


def test_detail_batch_rejects_more_than_50_candidates_without_silent_truncation():
    retrieval, _ = make_services()
    identity = IdentityContext(user_id=1, role="HR_ADMIN")

    with pytest.raises(ValueError):
        retrieval.get_safe_detail_batch(
            candidate_ids=list(range(100)),
            return_fields=["name"],
            identity=identity,
        )


def test_query_facts_returns_aggregate_without_contact_fields():
    retrieval, query = make_services()
    identity = IdentityContext(user_id=1, role="READONLY_VIEWER")

    result = query.query_facts(
        metrics=["count"],
        filters={},
        group_by=["position_name", "status", "source_name"],
        identity=identity,
    )

    assert result["count"] == 2
    assert retrieval.repository.search_calls == []
    assert "mobile" not in str(result)
    assert "email" not in str(result)
    assert {row["position_name"] for row in result["position_distribution"]} == {"芯片建模工程师", "应用软件开发工程师"}


def test_query_facts_supports_extended_group_by_dimensions():
    _, query = make_services()
    identity = IdentityContext(user_id=1, role="HR_ADMIN")

    result = query.query_facts(
        metrics=["count"],
        filters={"proposed_join_date_from": "2026-06-01", "proposed_join_date_to": "2026-06-30"},
        group_by=["gender", "work_years_band", "proposed_join_month"],
        identity=identity,
    )

    assert result["gender_distribution"]
    assert result["work_years_band_distribution"]
    assert result["proposed_join_month_distribution"]




def test_readonly_viewer_cannot_retrieve_candidate_profiles():
    retrieval, _ = make_services()
    identity = IdentityContext(user_id=9, role="READONLY_VIEWER")

    result = retrieval.search_safe_profiles(
        filters={},
        return_fields=["name", "gender", "status"],
        page_size=10,
        identity=identity,
    )

    assert result["candidates"] == []
    assert result["total_count"] == 0


@pytest.mark.parametrize(
    "identity",
    [
        IdentityContext(user_id=2, role="RECRUITER"),
        IdentityContext(user_id=8, role="DEPARTMENT_MANAGER", department_id=7),
        IdentityContext(user_id=42, role="INTERVIEWER"),
    ],
)
def test_business_roles_can_retrieve_full_safe_candidate_pool(identity):
    retrieval, _ = make_services()

    result = retrieval.search_safe_profiles(
        filters={},
        return_fields=["candidate_id", "name"],
        page_size=10,
        identity=identity,
    )

    assert result["candidates"] == [
        {"candidate_id": 1, "name": "张三"},
        {"candidate_id": 2, "name": "李四"},
    ]
    assert result["total_count"] == 2
    assert retrieval.repository.search_calls[-1]["identity_scope"] == {}


def test_query_facts_uses_full_safe_pool_for_recruiter_aggregates():
    retrieval, query = make_services()
    identity = IdentityContext(user_id=2, role="RECRUITER")

    result = query.query_facts(
        metrics=["count"],
        filters={},
        group_by=["position_name", "status"],
        identity=identity,
    )

    assert result["count"] == 2
    assert retrieval.repository.search_calls == []
    assert retrieval.repository.count_calls[-1]["identity_scope"] == {}
    assert result["position_distribution"] == [
        {"position_name": "应用软件开发工程师", "count": 1},
        {"position_name": "芯片建模工程师", "count": 1},
    ]
    assert result["status_distribution"] == [
        {"status": "REJECTED", "count": 1},
        {"status": "SCREEN_PROCESS", "count": 1},
    ]
