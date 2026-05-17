"""内网部署资产测试。

该文件验证部署脚本、systemd unit、内网配置示例和 Claude Code 文档使用统一的生产目录。
这些测试不启动服务、不访问真实数据库，只保护部署材料不会回退到旧共享路径或误导用户使用本地 dump。
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_BASE = "/workspace/devops/env_prod/service/ai/hr_mcp"
OLD_BASE = "/workspace/devops/pkgs/ai/hr_mcp"


def read(relative_path):
    # type: (str) -> str
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_deploy_scripts_use_intranet_production_base_path():
    expected_paths = [
        "deploy/package_release.sh",
        "deploy/package_release.ps1",
        "deploy/hr-mcp.service",
        "deploy/start_hr_mcp_nohup.sh",
        "deploy/stop_hr_mcp_nohup.sh",
        "deploy/check_hr_mcp.sh",
        "docs/intranet_deploy_fastapi_py36.md",
    ]

    for relative_path in expected_paths:
        text = read(relative_path)
        assert DEPLOY_BASE in text
        assert OLD_BASE not in text


def test_systemd_unit_uses_shared_venv_and_app_working_directory():
    unit = read("deploy/hr-mcp.service")

    assert "WorkingDirectory=%s/app" % DEPLOY_BASE in unit
    assert "EnvironmentFile=%s/.env" % DEPLOY_BASE in unit
    assert "Environment=HR_MCP_ENV_PATH=%s/.env" % DEPLOY_BASE in unit
    assert "ExecStart=%s/venv_py36/bin/python -m hr_mcp" % DEPLOY_BASE in unit
    assert "Restart=always" in unit
    assert "StandardOutput=journal" in unit
    assert "append:" not in unit
    assert "User=marc" in unit


def test_nohup_script_points_service_to_base_env_without_sourcing_secrets():
    script = read("deploy/start_hr_mcp_nohup.sh")

    assert 'export HR_MCP_ENV_PATH="$ENV_FILE"' in script
    assert '. "$ENV_FILE"' not in script
    assert "source \"$ENV_FILE\"" not in script


def test_release_packaging_script_uses_git_archive_and_requires_clean_tree():
    script = read("deploy/package_release.sh")

    assert "git status --porcelain" in script
    assert "Working tree is not clean" in script
    assert "git archive --format=zip" in script
    assert "NoMachine" in script
    doc_section = read("docs/intranet_deploy_fastapi_py36.md").split("## 2. 拷贝代码", 1)[1].split("## 3.", 1)[0]
    assert "bash ./deploy/package_release.sh" in doc_section
    assert "反斜杠会被 Bash 当作转义字符" in doc_section


def test_intranet_runbook_describes_nomachine_transfer_boundary():
    doc = read("docs/intranet_deploy_fastapi_py36.md")

    assert "NoMachine" in doc
    assert "nx2" in doc
    assert "外网 Windows 本地" in doc
    assert "不要在外网本地执行" in doc


def test_intranet_env_example_requires_mysql_and_logs_paths():
    env_example = read(".env.intranet.example")

    assert "HR_DATA_BACKEND=mysql" in env_example
    assert "HR_DATA_BACKEND=dump" not in env_example
    assert "HR_AUTH_TOKENS_PATH=%s/config/auth_tokens.json" % DEPLOY_BASE in env_example
    assert "HR_AUDIT_PATH=%s/logs/audit.jsonl" % DEPLOY_BASE in env_example
    assert "HR_RESULT_PATH=%s/logs/screening_results.jsonl" % DEPLOY_BASE in env_example
    assert "HR_DB_PASSWORD=replace-in-intranet-env" in env_example


def test_check_script_covers_health_ready_tools_and_facts_without_jq():
    script = read("deploy/check_hr_mcp.sh")

    assert "/healthz" in script
    assert "/readyz" in script
    assert "\"method\":\"tools/list\"" in script
    assert "query_talent_pool_facts" in script
    assert "jq" not in script.lower()
