"""字段权限策略测试。

该文件验证默认 Agent 可见字段、高权限字段、不可见字段和访问理由要求。
测试明确保证候选人姓名、性别和拟入职时间原文返回，同时联系方式不会进入默认上下文。
这些用例是字段白名单模型的回归保护。
"""

from pathlib import Path

import pytest

from hr_mcp.models.context import IdentityContext
from hr_mcp.security.field_policy import (
    DEFAULT_VISIBLE_FIELDS,
    PRIVILEGED_ROLES,
    PRIVILEGED_VISIBLE_FIELDS,
    FieldAccessError,
    FieldPolicy,
)
from hr_mcp.services.candidate_safe_view_service import CandidateSafeViewService
from hr_mcp.services.permission_service import PermissionService


def test_default_agent_fields_allow_candidate_name_gender_and_join_date():
    policy = FieldPolicy()

    allowed = policy.allowed_fields(
        "hr_candidate",
        ["candidate_id", "name", "gender", "proposed_join_date"],
        role="RECRUITER",
        access_reason=None,
    )

    assert allowed == ["candidate_id", "name", "gender", "proposed_join_date"]


def test_default_agent_fields_allow_position_name_and_jd_in_candidate_profile():
    policy = FieldPolicy()

    allowed = policy.allowed_fields(
        "hr_candidate",
        ["candidate_id", "position_name", "position_jd"],
        role="RECRUITER",
        access_reason=None,
    )

    assert allowed == ["candidate_id", "position_name", "position_jd"]


def test_field_policy_loads_project_yaml_consistently(tmp_path):
    policy_file = tmp_path / "field_policy.yml"
    policy_file.write_text(
        "default_visible:\n"
        "  hr_candidate:\n"
        "    - candidate_id\n"
        "    - name\n"
        "  sys_org: [name]\n"
        "privileged_visible:\n"
        "  hr_candidate: [mobile, email]\n"
        "privileged_roles: [HR_ADMIN, SECURITY_ADMIN]\n",
        encoding="utf-8",
    )

    policy = FieldPolicy.from_yaml(policy_file)

    assert policy.default_fields["hr_candidate"] == {"candidate_id", "name"}
    assert policy.privileged_fields["hr_candidate"] == {"mobile", "email"}
    assert policy.privileged_roles == {"HR_ADMIN", "SECURITY_ADMIN"}


def test_project_field_policy_yaml_matches_runtime_defaults():
    project_root = Path(__file__).resolve().parents[1]
    policy = FieldPolicy.from_yaml(project_root / "config" / "field_policy.yml")

    assert policy.default_fields == {key: set(value) for key, value in DEFAULT_VISIBLE_FIELDS.items()}
    assert policy.privileged_fields == {key: set(value) for key, value in PRIVILEGED_VISIBLE_FIELDS.items()}
    assert policy.privileged_roles == set(PRIVILEGED_ROLES)


def test_high_privilege_fields_require_privileged_role_and_access_reason():
    policy = FieldPolicy()

    with pytest.raises(FieldAccessError):
        policy.allowed_fields(
            "hr_candidate",
            ["mobile", "email"],
            role="RECRUITER",
            access_reason="联系候选人",
        )

    with pytest.raises(FieldAccessError):
        policy.allowed_fields(
            "hr_candidate",
            ["mobile", "email"],
            role="HR_ADMIN",
            access_reason=None,
        )

    assert policy.allowed_fields(
        "hr_candidate",
        ["mobile", "email"],
        role="HR_ADMIN",
        access_reason="联系候选人",
    ) == ["mobile", "email"]


def test_unlisted_fields_are_never_visible_to_agent():
    policy = FieldPolicy()

    with pytest.raises(FieldAccessError):
        policy.allowed_fields(
            "hr_candidate",
            ["resume_file"],
            role="HR_ADMIN",
            access_reason="debug",
        )


def test_safe_view_projects_only_requested_allowed_fields():
    service = CandidateSafeViewService(
        field_policy=FieldPolicy(),
        permission_service=PermissionService(),
    )
    identity = IdentityContext(user_id=2, role="RECRUITER")
    record = {
        "id": 100,
        "candidate_id": 100,
        "name": "张三",
        "gender": "MALE",
        "proposed_join_date": "2026-06-01",
        "mobile": "13800000000",
    }

    projected = service.project_record(
        "hr_candidate",
        record,
        ["candidate_id", "name", "gender", "proposed_join_date"],
        identity,
    )

    assert projected == {
        "candidate_id": 100,
        "name": "张三",
        "gender": "MALE",
        "proposed_join_date": "2026-06-01",
    }
    assert "mobile" not in projected


def test_safe_view_can_include_privileged_fields_for_admin_with_reason():
    service = CandidateSafeViewService(
        field_policy=FieldPolicy(),
        permission_service=PermissionService(),
    )
    identity = IdentityContext(user_id=1, role="HR_ADMIN", access_reason="联系候选人")
    record = {"name": "张三", "mobile": "13800000000", "email": "z@example.com"}

    projected = service.project_record(
        "hr_candidate",
        record,
        ["name", "mobile", "email"],
        identity,
    )

    assert projected == {"name": "张三", "mobile": "13800000000", "email": "z@example.com"}


def test_candidate_safe_view_service_does_not_import_repository_layer():
    import inspect
    import hr_mcp.services.candidate_safe_view_service as module

    source = inspect.getsource(module)
    assert "repositories" not in source
    assert "mysql_repository" not in source
    assert "dump_repository" not in source
