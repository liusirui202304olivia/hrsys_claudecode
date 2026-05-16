"""HTTP MCP 应用测试。

该文件通过内存方式调用 HTTP app，验证健康检查、就绪检查、MCP tools/list、tools/call 和调试工具清单权限。
它还模拟 Gateway header，确认高权限字段访问、READONLY 明细限制和 Gateway shared secret 防伪逻辑生效。
测试避免真实网络依赖，但覆盖 HTTP 层到安全数据服务层的主要请求路径。
"""

import json
from pathlib import Path

from hr_mcp.http.app import create_app
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


def make_project(tmp_path: Path) -> Path:
    dump_dir = tmp_path / "hr_data_sample"
    standard_dir = tmp_path / "standard_markdown"
    dump_dir.mkdir(parents=True)
    standard_dir.mkdir(parents=True)
    (dump_dir / "devops_hr_user_data_0508_1.sql").write_text(SAMPLE_DUMP, encoding="utf-8")
    (standard_dir / "chip.md").write_text("# 芯片建模工程师筛选标准\n- C++\n- gem5", encoding="utf-8")
    return tmp_path


def test_healthz_readyz_and_admin_tools_endpoint(tmp_path: Path):
    app = create_app(ConfigCenter(project_root=make_project(tmp_path)))

    assert app.handle_request("GET", "/healthz", {}, b"")[0] == 200
    ready_status, ready_body = app.handle_request("GET", "/readyz", {}, b"")
    tools_status, tools_body = app.handle_request("GET", "/mcp/tools", {"X-User-Role": "HR_ADMIN"}, b"")

    assert ready_status == 200
    assert ready_body["checks"]["database"] is True
    assert "standard_markdown" not in ready_body["checks"]
    assert tools_status == 200
    assert len(tools_body["tools"]) == 4


def test_mcp_tools_list_and_facts_call(tmp_path: Path):
    app = create_app(ConfigCenter(project_root=make_project(tmp_path)))

    list_status, list_body = app.handle_request(
        "POST",
        "/mcp",
        {"X-User-Role": "HR_ADMIN"},
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode("utf-8"),
    )
    call_status, call_body = app.handle_request(
        "POST",
        "/mcp",
        {"X-User-Role": "HR_ADMIN"},
        json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "query_talent_pool_facts", "arguments": {"metrics": ["count"], "group_by": ["position_name"]}},
        }).encode("utf-8"),
    )

    assert list_status == 200
    assert [tool["name"] for tool in list_body["result"]["tools"]] == [
        "search_candidate_safe_profiles",
        "get_candidate_safe_detail_batch",
        "query_talent_pool_facts",
        "save_screening_result",
    ]
    assert call_status == 200
    assert call_body["result"]["facts"]["count"] == 1


def test_search_result_candidate_id_can_be_reused_to_save_screening_result(tmp_path: Path):
    app = create_app(ConfigCenter(project_root=make_project(tmp_path)))

    search_status, search_body = app.handle_request(
        "POST",
        "/mcp",
        {"X-User-Role": "HR_ADMIN"},
        json.dumps({
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "search_candidate_safe_profiles",
                "arguments": {
                    "filters": {"position_query": "芯片建模"},
                    "return_fields": ["candidate_id", "name"],
                    "limit": 5,
                },
            },
        }).encode("utf-8"),
    )
    candidate_id = search_body["result"]["candidates"][0]["candidate_id"]

    save_status, save_body = app.handle_request(
        "POST",
        "/mcp",
        {"X-User-Role": "HR_ADMIN"},
        json.dumps({
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
        }).encode("utf-8"),
    )

    assert search_status == 200
    assert candidate_id == 1
    assert save_status == 200
    assert save_body["result"]["saved"]["recommended_candidates"][0]["candidate_id"] == 1


def test_gateway_headers_control_privileged_candidate_fields(tmp_path: Path):
    app = create_app(ConfigCenter(project_root=make_project(tmp_path)))
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "search_candidate_safe_profiles",
            "arguments": {
                "filters": {"position_query": "芯片建模"},
                "return_fields": ["name", "gender", "proposed_join_date", "mobile"],
                "limit": 5,
            },
        },
    }).encode("utf-8")

    blocked_status, blocked_body = app.handle_request("POST", "/mcp", {"X-User-Role": "RECRUITER"}, payload)
    allowed_status, allowed_body = app.handle_request(
        "POST",
        "/mcp",
        {"X-User-Role": "HR_ADMIN", "X-Access-Reason": "联系候选人"},
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
    app = create_app(ConfigCenter(project_root=make_project(tmp_path)))

    status, body = app.handle_request("GET", "/mcp/tools", {"X-User-Role": "READONLY_VIEWER"}, b"")

    assert status == 403
    assert body["error"] == "forbidden"


def test_mcp_rejects_untrusted_gateway_headers_when_secret_configured(tmp_path: Path):
    project_root = make_project(tmp_path)
    env_file = project_root / ".env"
    env_file.write_text("HR_GATEWAY_SHARED_SECRET=s3cr3t\n", encoding="utf-8")
    app = create_app(ConfigCenter(project_root=project_root, env_path=env_file))

    status, body = app.handle_request(
        "POST",
        "/mcp",
        {"X-User-Role": "HR_ADMIN", "X-Access-Reason": "联系候选人"},
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode("utf-8"),
    )

    assert status == 401
    assert body["error"] == "unauthorized_gateway"
