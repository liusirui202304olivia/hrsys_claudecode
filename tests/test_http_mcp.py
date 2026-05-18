"""HTTP MCP 应用测试。

该文件通过内存方式调用 HTTP app，验证健康检查、就绪检查、HTTP-MCP JSON-RPC、
Bearer token 鉴权、IP 白名单、限流、请求体大小限制和调试接口权限。
测试避免真实网络依赖，但覆盖 HTTP 层到安全数据服务层的主要请求路径。
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from hr_mcp.http.app import create_app
from hr_mcp.mcp.jsonrpc import JsonRpcError
from hr_mcp.services.config_center import ConfigCenter


SAMPLE_DUMP = r'''
CREATE TABLE `hr_candidate` (
  `id` int NOT NULL AUTO_INCREMENT,
  `source_id` int NOT NULL COMMENT '简历来源',
  `position_id` int NOT NULL COMMENT '岗位ID',
  `status` varchar(50) NOT NULL COMMENT '状态',
  `hr_id` int NOT NULL COMMENT '责任HR',
  `name` varchar(100) DEFAULT NULL COMMENT '姓名',
  `gender` varchar(20) DEFAULT NULL COMMENT '性别',
  `degree_first` varchar(20) DEFAULT NULL COMMENT '第一学历',
  `degree` varchar(20) DEFAULT NULL COMMENT '最高学历',
  `college` varchar(500) DEFAULT NULL COMMENT '最高学历学校',
  `major` varchar(500) DEFAULT NULL COMMENT '最高学历专业',
  `work_years` int DEFAULT NULL COMMENT '工作年限',
  `experiences` json DEFAULT NULL COMMENT '履历',
  `proposed_join_date` date DEFAULT NULL COMMENT '拟入职时间',
  `mobile` varchar(30) DEFAULT NULL COMMENT '电话',
  `email` varchar(100) DEFAULT NULL COMMENT '邮箱',
  `skills` json DEFAULT (_utf8mb4'[]') COMMENT '技术栈',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='候选人';
INSERT INTO `hr_candidate` VALUES
(1,10,20,'SCREEN_PROCESS',2,'张三','MALE','BACHELOR','BACHELOR','四川大学','计算机',5,'[]','2026-06-01','13800000000','zhang@example.com','["C++","gem5"]');

CREATE TABLE `hr_position` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL COMMENT '岗位名称',
  `category` varchar(20) NOT NULL COMMENT '岗位类别',
  `jd` text NOT NULL COMMENT '职位描述',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='岗位';
INSERT INTO `hr_position` VALUES (20,'芯片建模工程师','DEV','负责CPU性能建模',1);

CREATE TABLE `hr_source` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `name` varchar(255) NOT NULL COMMENT '名称',
  `full_name` varchar(255) NOT NULL COMMENT '全称',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='简历来源';
INSERT INTO `hr_source` VALUES (10,'历史导入','其他/历史导入');
'''


def make_project(tmp_path: Path, env_text: str = "") -> Path:
    dump_dir = tmp_path / "hr_data_sample"
    standard_dir = tmp_path / "standard_markdown"
    config_dir = tmp_path / "config"
    dump_dir.mkdir(parents=True)
    standard_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    (dump_dir / "devops_hr_user_data_0508_1.sql").write_text(SAMPLE_DUMP, encoding="utf-8")
    (standard_dir / "chip.md").write_text("# 芯片建模工程师筛选标准\n- C++\n- gem5", encoding="utf-8")
    (config_dir / "auth_tokens.json").write_text(
        json.dumps({
            "tokens": {
                "admin-token": {"user_id": 1, "user_name": "Admin", "role": "HR_ADMIN", "department_id": 7},
                "recruiter-token": {"user_id": 2, "user_name": "Recruiter", "role": "RECRUITER", "department_id": 7},
                "viewer-token": {"user_id": 3, "user_name": "Viewer", "role": "READONLY_VIEWER", "department_id": 9},
            }
        }),
        encoding="utf-8",
    )
    if env_text:
        (tmp_path / ".env").write_text(env_text, encoding="utf-8")
    return tmp_path


def make_app(tmp_path: Path, env_text: str = "HR_DATA_BACKEND=dump\n"):
    if "HR_DATA_BACKEND" not in env_text:
        env_text = "HR_DATA_BACKEND=dump\n" + env_text
    project_root = make_project(tmp_path, env_text)
    return create_app(ConfigCenter(project_root=project_root))


def auth(token: str, extra=None):
    headers = {"Authorization": "Bearer " + token, "X-Forwarded-For": "127.0.0.1"}
    if extra:
        headers.update(extra)
    return headers


def rpc_body(payload):
    return json.dumps(payload).encode("utf-8")


def tools_list_payload():
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}


def search_payload(return_fields=None):
    return {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "search_candidate_safe_profiles",
            "arguments": {
                "filters": {"position_query": "芯片建模"},
                "return_fields": return_fields or ["candidate_id", "name"],
                "limit": 5,
            },
        },
    }


def test_healthz_readyz_and_admin_tools_endpoint(tmp_path: Path):
    app = make_app(tmp_path)

    assert app.handle_request("GET", "/healthz", {}, b"")[0] == 200
    ready_status, ready_body = app.handle_request("GET", "/readyz", {}, b"")
    tools_status, tools_body = app.handle_request("GET", "/mcp/tools", auth("admin-token"), b"")

    assert ready_status == 200
    assert ready_body["checks"]["database"] is True
    assert "standard_markdown" not in ready_body["checks"]
    assert tools_status == 200
    assert len(tools_body["tools"]) == 6


def test_fastapi_routes_delegate_to_same_http_mcp_logic(tmp_path: Path):
    app = make_app(tmp_path)
    client = TestClient(app.as_fastapi())

    health = client.get("/healthz")
    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer admin-token"},
        json=tools_list_payload(),
    )

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert response.status_code == 200
    assert response.json()["result"]["tools"][0]["name"] == "search_candidate_safe_profiles"


def test_mcp_requires_valid_bearer_token(tmp_path: Path):
    app = make_app(tmp_path)

    missing_status, missing_body = app.handle_request("POST", "/mcp", {}, rpc_body(tools_list_payload()))
    bad_status, bad_body = app.handle_request("POST", "/mcp", auth("bad-token"), rpc_body(tools_list_payload()))

    assert missing_status == 401
    assert missing_body["error"] == "unauthorized"
    assert bad_status == 401
    assert bad_body["error"] == "unauthorized"


def test_mcp_tools_list_and_facts_call(tmp_path: Path):
    app = make_app(tmp_path)

    list_status, list_body = app.handle_request("POST", "/mcp", auth("admin-token"), rpc_body(tools_list_payload()))
    call_status, call_body = app.handle_request(
        "POST",
        "/mcp",
        auth("admin-token"),
        rpc_body({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "query_talent_pool_facts", "arguments": {"metrics": ["count"], "group_by": ["position_name"]}},
        }),
    )

    assert list_status == 200
    assert [tool["name"] for tool in list_body["result"]["tools"]] == [
        "search_candidate_safe_profiles",
        "get_candidate_safe_detail_batch",
        "query_talent_pool_facts",
        "query_hr_safe_sql",
        "describe_hr_safe_schema",
        "save_screening_result",
    ]
    assert call_status == 200
    assert call_body["result"]["facts"]["count"] == 1


def test_mcp_safe_sql_supports_open_ended_candidate_lookup(tmp_path: Path):
    app = make_app(tmp_path)

    status, body = app.handle_request(
        "POST",
        "/mcp",
        auth("recruiter-token"),
        rpc_body({
            "jsonrpc": "2.0",
            "id": "safe-sql",
            "method": "tools/call",
            "params": {
                "name": "query_hr_safe_sql",
                "arguments": {
                    "purpose": "按姓名查看候选人信息",
                    "sql": "SELECT candidate_id, name, status, proposed_join_date FROM v_candidate_agent_safe WHERE candidate_id = 1",
                },
            },
        }),
    )

    assert status == 200
    assert body["result"]["row_count"] == 1
    assert body["result"]["rows"][0]["name"] == "张三"
    assert body["result"]["limit"] == 300


def test_mcp_safe_sql_rejects_raw_table_access(tmp_path: Path):
    app = make_app(tmp_path)

    status, body = app.handle_request(
        "POST",
        "/mcp",
        auth("admin-token"),
        rpc_body({
            "jsonrpc": "2.0",
            "id": "unsafe-sql",
            "method": "tools/call",
            "params": {
                "name": "query_hr_safe_sql",
                "arguments": {
                    "purpose": "尝试原表",
                    "sql": "SELECT candidate_id, name FROM hr_candidate LIMIT 10",
                },
            },
        }),
    )

    assert status == 200
    assert body["error"]["code"] == JsonRpcError.INVALID_REQUEST


def test_search_result_candidate_id_can_be_reused_to_save_screening_result(tmp_path: Path):
    app = make_app(tmp_path)

    search_status, search_body = app.handle_request("POST", "/mcp", auth("admin-token"), rpc_body(search_payload()))
    candidate_id = search_body["result"]["candidates"][0]["candidate_id"]

    save_status, save_body = app.handle_request(
        "POST",
        "/mcp",
        auth("admin-token"),
        rpc_body({
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "save_screening_result",
                "arguments": {
                    "task_id": "screen-1",
                    "standard_ref": "standard_markdown/yihai.md#CPU性能建模工程师",
                    "recommended_candidates": [{
                        "candidate_id": candidate_id,
                        "recommend_reason": "安全画像和岗位标准匹配",
                        "risk_points": ["需确认项目主导性"],
                    }],
                },
            },
        }),
    )

    assert search_status == 200
    assert candidate_id == 1
    assert save_status == 200
    assert save_body["result"]["saved"]["recommended_candidates"][0]["candidate_id"] == 1


def test_bearer_identity_controls_privileged_candidate_fields_and_ignores_spoofed_role(tmp_path: Path):
    app = make_app(tmp_path)
    payload = rpc_body(search_payload(["name", "gender", "proposed_join_date", "mobile"]))

    blocked_status, blocked_body = app.handle_request(
        "POST",
        "/mcp",
        auth("recruiter-token", {"X-User-Role": "HR_ADMIN", "X-Access-Reason": "contact candidate"}),
        payload,
    )
    allowed_status, allowed_body = app.handle_request(
        "POST",
        "/mcp",
        auth("admin-token", {"X-Access-Reason": "contact candidate"}),
        payload,
    )

    assert blocked_status == 200
    assert "error" in blocked_body
    assert allowed_status == 200
    candidate = allowed_body["result"]["candidates"][0]
    assert candidate["name"] == "张三"
    assert candidate["gender"] == "MALE"
    assert candidate["proposed_join_date"] == "2026-06-01"
    assert candidate["mobile"] == "13800000000"


def test_non_admin_tools_endpoint_is_forbidden(tmp_path: Path):
    app = make_app(tmp_path)

    status, body = app.handle_request("GET", "/mcp/tools", auth("viewer-token"), b"")

    assert status == 403
    assert body["error"] == "forbidden"


def test_ip_allowlist_blocks_non_internal_clients(tmp_path: Path):
    app = make_app(tmp_path, "HR_ALLOWED_IP_CIDRS=127.0.0.1/32\n")

    status, body = app.handle_request(
        "POST",
        "/mcp",
        auth("admin-token", {"X-Forwarded-For": "10.1.2.3"}),
        rpc_body(tools_list_payload()),
    )

    assert status == 403
    assert body["error"] == "ip_forbidden"


def test_rate_limit_blocks_repeated_calls_per_user(tmp_path: Path):
    app = make_app(tmp_path, "HR_RATE_LIMIT_PER_MINUTE=1\n")

    first_status, _ = app.handle_request("POST", "/mcp", auth("admin-token"), rpc_body(tools_list_payload()))
    second_status, second_body = app.handle_request("POST", "/mcp", auth("admin-token"), rpc_body(tools_list_payload()))

    assert first_status == 200
    assert second_status == 429
    assert second_body["error"] == "rate_limited"


def test_request_body_size_limit_blocks_large_payload(tmp_path: Path):
    app = make_app(tmp_path, "HR_MAX_REQUEST_BYTES=20\n")

    status, body = app.handle_request("POST", "/mcp", auth("admin-token"), rpc_body(tools_list_payload()))

    assert status == 413
    assert body["error"] == "request_too_large"
