"""身份解析与配置中心测试。

该文件验证 Gateway header 能构造 IdentityContext、本地 mock identity、默认最小权限和配置路径解析。
它还覆盖 Gateway shared secret 配置，确保服务端可拒绝未受信 Gateway 的伪造角色 header。
这些测试保护身份上下文作为后续权限判断输入的可信度。
"""

from pathlib import Path

from hr_mcp.services.config_center import ConfigCenter
from hr_mcp.services.identity_service import IdentityError, IdentityService


def test_gateway_headers_create_identity_context():
    service = IdentityService()
    headers = {
        "X-Request-Id": "req-1",
        "X-Trace-Id": "trace-1",
        "X-User-Id": "42",
        "X-User-Name": "王五",
        "X-User-Role": "HR_ADMIN",
        "X-Department-Id": "7",
        "X-Client-Id": "claudecode",
        "X-Access-Reason": "联系候选人",
    }

    identity = service.from_headers(headers)

    assert identity.user_id == 42
    assert identity.user_name == "王五"
    assert identity.role == "HR_ADMIN"
    assert identity.department_id == 7
    assert identity.client_id == "claudecode"
    assert identity.request_id == "req-1"
    assert identity.trace_id == "trace-1"
    assert identity.access_reason == "联系候选人"
    assert identity.mock_gateway_identity is False


def test_missing_role_uses_readonly_viewer():
    identity = IdentityService().from_headers({"X-User-Id": "5"})

    assert identity.user_id == 5
    assert identity.role == "READONLY_VIEWER"


def test_config_center_builds_mock_identity_when_enabled(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "HR_MOCK_IDENTITY_ENABLED=true\n"
        "HR_MOCK_USER_ID=9\n"
        "HR_MOCK_USER_NAME=Mock HR\n"
        "HR_MOCK_USER_ROLE=RECRUITER\n"
        "HR_MOCK_DEPARTMENT_ID=3\n",
        encoding="utf-8",
    )

    config = ConfigCenter(project_root=tmp_path, env_path=env_file)
    identity = IdentityService(config).from_headers({})

    assert identity.user_id == 9
    assert identity.user_name == "Mock HR"
    assert identity.role == "RECRUITER"
    assert identity.department_id == 3
    assert identity.mock_gateway_identity is True


def test_config_center_exposes_default_paths(tmp_path: Path):
    config = ConfigCenter(project_root=tmp_path)

    assert config.audit_path == tmp_path / "runtime" / "audit" / "audit.jsonl"
    assert config.result_path == tmp_path / "runtime" / "results" / "screening_results.jsonl"
    assert config.dump_path == tmp_path / "hr_data_sample" / "devops_hr_user_data_0508_1.sql"



def test_gateway_shared_secret_required_when_configured(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("HR_GATEWAY_SHARED_SECRET=s3cr3t\n", encoding="utf-8")
    service = IdentityService(ConfigCenter(project_root=tmp_path, env_path=env_file))

    try:
        service.from_headers({"X-User-Role": "HR_ADMIN"})
        raised = False
    except IdentityError:
        raised = True

    assert raised is True
    identity = service.from_headers({"X-User-Role": "HR_ADMIN", "X-Gateway-Secret": "s3cr3t"})
    assert identity.role == "HR_ADMIN"
