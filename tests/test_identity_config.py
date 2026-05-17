"""身份解析与配置中心测试。

该文件验证中心化 HTTP-MCP 服务通过服务端 Bearer token 配置构造 IdentityContext。
测试确保客户端不能通过伪造身份 header 提权，同时保留本地 mock identity 作为开发兜底。
这些用例保护身份上下文作为后续权限判断输入的可信度。
"""

import json
from pathlib import Path

import pytest

from hr_mcp.services.config_center import ConfigCenter
from hr_mcp.services.identity_service import IdentityError, IdentityService


def write_auth_tokens(project_root: Path) -> Path:
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    token_file = config_dir / "auth_tokens.json"
    token_file.write_text(
        json.dumps({
            "tokens": {
                "admin-token": {
                    "user_id": 42,
                    "user_name": "Wang Wu",
                    "role": "HR_ADMIN",
                    "department_id": 7,
                },
                "viewer-token": {
                    "user_id": 5,
                    "user_name": "Viewer",
                    "role": "READONLY_VIEWER",
                    "department_id": 9,
                },
            }
        }),
        encoding="utf-8",
    )
    return token_file


def test_bearer_token_creates_identity_context(tmp_path: Path):
    write_auth_tokens(tmp_path)
    service = IdentityService(ConfigCenter(project_root=tmp_path))
    headers = {
        "Authorization": "Bearer admin-token",
        "X-Request-Id": "req-1",
        "X-Trace-Id": "trace-1",
        "X-Client-Id": "claudecode",
        "X-Access-Reason": "contact candidate",
    }

    identity = service.from_headers(headers)

    assert identity.user_id == 42
    assert identity.user_name == "Wang Wu"
    assert identity.role == "HR_ADMIN"
    assert identity.department_id == 7
    assert identity.client_id == "claudecode"
    assert identity.request_id == "req-1"
    assert identity.trace_id == "trace-1"
    assert identity.access_reason == "contact candidate"
    assert identity.mock_gateway_identity is False


def test_client_identity_headers_do_not_override_token_identity(tmp_path: Path):
    write_auth_tokens(tmp_path)
    service = IdentityService(ConfigCenter(project_root=tmp_path))

    identity = service.from_headers({
        "Authorization": "Bearer viewer-token",
        "X-User-Id": "42",
        "X-User-Role": "HR_ADMIN",
        "X-Department-Id": "7",
    })

    assert identity.user_id == 5
    assert identity.role == "READONLY_VIEWER"
    assert identity.department_id == 9


def test_missing_or_unknown_bearer_token_is_rejected(tmp_path: Path):
    write_auth_tokens(tmp_path)
    service = IdentityService(ConfigCenter(project_root=tmp_path))

    for headers in [{}, {"Authorization": "Bearer bad-token"}]:
        try:
            service.from_headers(headers)
            raised = False
        except IdentityError:
            raised = True
        assert raised is True


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
    assert config.auth_tokens_path == tmp_path / "config" / "auth_tokens.json"


def test_config_center_exposes_intranet_security_config(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "HR_AUTH_TOKENS_PATH=config/custom_tokens.json\n"
        "HR_AUDIT_PATH=logs/audit.jsonl\n"
        "HR_RESULT_PATH=logs/results.jsonl\n"
        "HR_ALLOWED_IP_CIDRS=127.0.0.1/32,10.0.0.0/8\n"
        "HR_RATE_LIMIT_PER_MINUTE=10\n"
        "HR_MAX_REQUEST_BYTES=2048\n",
        encoding="utf-8",
    )
    config = ConfigCenter(project_root=tmp_path, env_path=env_file)

    assert config.auth_tokens_path == tmp_path / "config" / "custom_tokens.json"
    assert config.audit_path == tmp_path / "logs" / "audit.jsonl"
    assert config.result_path == tmp_path / "logs" / "results.jsonl"
    assert config.allowed_ip_cidrs == ["127.0.0.1/32", "10.0.0.0/8"]
    assert config.rate_limit_per_minute == 10
    assert config.max_request_bytes == 2048


def test_data_backend_must_be_explicitly_configured(tmp_path: Path):
    config = ConfigCenter(project_root=tmp_path)

    with pytest.raises(ValueError, match="HR_DATA_BACKEND"):
        _ = config.data_backend


def test_data_backend_accepts_only_explicit_mysql_or_dump(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("HR_DATA_BACKEND=dump\n", encoding="utf-8")
    assert ConfigCenter(project_root=tmp_path, env_path=env_file).data_backend == "dump"

    env_file.write_text("HR_DATA_BACKEND=mysql\n", encoding="utf-8")
    assert ConfigCenter(project_root=tmp_path, env_path=env_file).data_backend == "mysql"

    env_file.write_text("HR_DATA_BACKEND=sqlite\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported HR_DATA_BACKEND"):
        _ = ConfigCenter(project_root=tmp_path, env_path=env_file).data_backend
