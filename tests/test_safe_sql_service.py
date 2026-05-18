"""Safe SQL sandbox service tests.

These tests define the contract for the open-ended HR data query path. The
backend may execute Agent-authored SQL only after it proves the statement is a
single read-only SELECT over approved safe views, with field visibility,
privileged access, row limits, and audit-friendly metadata enforced before the
repository sees the SQL.
"""

import pytest

from hr_mcp.models.context import IdentityContext
from hr_mcp.security.field_policy import FieldAccessError, FieldPolicy
from hr_mcp.services.safe_sql_service import SafeSqlService, SafeSqlValidationError


class RecordingRepository:
    def __init__(self):
        self.calls = []

    def execute_safe_sql(self, sql):
        self.calls.append(sql)
        return [{"candidate_id": 1, "name": "张三"}]


def make_service():
    repo = RecordingRepository()
    service = SafeSqlService(repo, FieldPolicy())
    return service, repo


def test_safe_sql_allows_select_from_safe_view_and_adds_default_limit():
    service, repo = make_service()
    identity = IdentityContext(user_id=1, role="RECRUITER")

    result = service.query(
        "SELECT candidate_id, name FROM v_candidate_agent_safe WHERE name LIKE '%张%'",
        identity,
    )

    assert result["rows"] == [{"candidate_id": 1, "name": "张三"}]
    assert result["row_count"] == 1
    assert result["view"] == "v_candidate_agent_safe"
    assert result["limit"] == 300
    assert repo.calls == [
        "SELECT candidate_id, name FROM v_candidate_agent_safe WHERE name LIKE '%张%' LIMIT 300"
    ]


def test_safe_sql_preserves_valid_explicit_limit():
    service, repo = make_service()
    identity = IdentityContext(user_id=1, role="RECRUITER")

    result = service.query("SELECT candidate_id, name FROM v_candidate_agent_safe LIMIT 10", identity)

    assert result["limit"] == 10
    assert repo.calls[-1] == "SELECT candidate_id, name FROM v_candidate_agent_safe LIMIT 10"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT candidate_id FROM hr_candidate LIMIT 10",
        "SELECT candidate_id FROM information_schema.tables LIMIT 10",
        "UPDATE v_candidate_agent_safe SET name='x'",
        "SELECT candidate_id FROM v_candidate_agent_safe; SELECT 1",
        "SELECT candidate_id FROM v_candidate_agent_safe -- comment\nLIMIT 10",
        "SELECT SLEEP(1) FROM v_candidate_agent_safe LIMIT 10",
        "SELECT LOAD_FILE('/etc/passwd') FROM v_candidate_agent_safe LIMIT 10",
        "SELECT candidate_id FROM v_candidate_agent_safe INTO OUTFILE '/tmp/x'",
    ],
)
def test_safe_sql_rejects_unsafe_sql(sql):
    service, repo = make_service()
    identity = IdentityContext(user_id=1, role="RECRUITER")

    with pytest.raises(SafeSqlValidationError):
        service.query(sql, identity)

    assert repo.calls == []


def test_safe_sql_rejects_fields_not_visible_to_default_roles():
    service, repo = make_service()
    identity = IdentityContext(user_id=1, role="RECRUITER")

    with pytest.raises(FieldAccessError):
        service.query("SELECT candidate_id, mobile FROM v_candidate_agent_privileged LIMIT 10", identity)

    assert repo.calls == []


def test_safe_sql_requires_access_reason_for_privileged_view():
    service, repo = make_service()
    identity = IdentityContext(user_id=1, role="HR_ADMIN")

    with pytest.raises(FieldAccessError):
        service.query("SELECT candidate_id, mobile FROM v_candidate_agent_privileged LIMIT 10", identity)

    assert repo.calls == []


def test_safe_sql_allows_privileged_view_for_admin_with_access_reason():
    service, repo = make_service()
    identity = IdentityContext(user_id=1, role="HR_ADMIN", access_reason="联系候选人")

    result = service.query("SELECT candidate_id, mobile FROM v_candidate_agent_privileged LIMIT 10", identity)

    assert result["view"] == "v_candidate_agent_privileged"
    assert result["privileged"] is True
    assert repo.calls[-1] == "SELECT candidate_id, mobile FROM v_candidate_agent_privileged LIMIT 10"


def test_safe_sql_rejects_limit_above_service_cap():
    service, repo = make_service()
    identity = IdentityContext(user_id=1, role="RECRUITER")

    with pytest.raises(SafeSqlValidationError):
        service.query("SELECT candidate_id FROM v_candidate_agent_safe LIMIT 301", identity)

    assert repo.calls == []


def test_safe_sql_allows_aggregate_and_alias_over_safe_fields():
    service, repo = make_service()
    identity = IdentityContext(user_id=1, role="READONLY_VIEWER")

    service.query(
        "SELECT DATE_FORMAT(proposed_join_date, '%Y-%m') AS join_month, COUNT(*) AS count "
        "FROM v_candidate_agent_safe GROUP BY join_month ORDER BY count DESC LIMIT 12",
        identity,
    )

    assert repo.calls[-1].startswith("SELECT DATE_FORMAT(proposed_join_date")


def test_describe_safe_schema_exposes_default_and_privileged_schema_metadata():
    service, _ = make_service()
    identity = IdentityContext(user_id=1, role="RECRUITER")

    schema = service.describe_schema(identity)

    safe_view = schema["views"]["v_candidate_agent_safe"]
    privileged_view = schema["views"]["v_candidate_agent_privileged"]
    assert "name" in safe_view["fields"]
    assert "proposed_join_date" in safe_view["fields"]
    assert "mobile" not in safe_view["fields"]
    assert "mobile" in privileged_view["privileged_fields"]
    assert privileged_view["requires_role"] == "HR_ADMIN"
