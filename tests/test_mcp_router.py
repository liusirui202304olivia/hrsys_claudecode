"""MCP 工具注册、路由与 JSON-RPC 测试。

该文件验证 4 个 MCP 安全数据工具清单、工具调用分发、审计记录、未知工具错误和 malformed params 的 JSON-RPC error code。
它还检查 ToolRouter 不 import repository，确保 MCP 层只做数据工具路由而不越层访问数据源。
保存推荐结果的角色授权也在这里做回归验证。
"""

import inspect

import pytest

from hr_mcp.mcp.jsonrpc import JsonRpcError, JsonRpcHandler
from hr_mcp.models.context import IdentityContext
from hr_mcp.services.tool_registry import ToolRegistry
from hr_mcp.services.tool_router import ToolRouter


class FakeRetrievalService:
    def search_safe_profiles(self, filters, return_fields, limit, identity):
        return [{"candidate_id": 1, "name": "张三"}]

    def get_safe_detail_batch(self, candidate_ids, return_fields, identity):
        return {"candidates": [{"candidate_id": candidate_ids[0], "name": "张三"}]}


class FakeTalentQueryService:
    def query_facts(self, metrics, filters, group_by, identity):
        return {"count": 2, "position_distribution": [{"position_name": "芯片建模", "count": 2}]}


class FakeResultStore:
    def save_screening_result(self, task_id, standard_ref, recommended_candidates, identity):
        return {"task_id": task_id, "standard_ref": standard_ref, "recommended_candidates": recommended_candidates, "saved": True}


class FakeAudit:
    def __init__(self):
        self.calls = []

    def record_tool_call(self, tool_name, arguments, result_summary, identity, candidate_ids=None, fields=None):
        self.calls.append({"tool_name": tool_name, "arguments": arguments, "fields": fields or []})
        return self.calls[-1]


def build_router():
    audit = FakeAudit()
    router = ToolRouter(
        registry=ToolRegistry(),
        retrieval_service=FakeRetrievalService(),
        talent_query_service=FakeTalentQueryService(),
        result_store=FakeResultStore(),
        audit_service=audit,
    )
    return router, audit


def test_registry_lists_four_data_tools():
    tools = ToolRegistry().list_tools()
    assert [tool["name"] for tool in tools] == [
        "search_candidate_safe_profiles",
        "get_candidate_safe_detail_batch",
        "query_talent_pool_facts",
        "save_screening_result",
    ]
    assert all("input_schema" in tool for tool in tools)


def test_router_calls_registered_tools_and_records_audit():
    router, audit = build_router()
    identity = IdentityContext(user_id=7, role="HR_ADMIN")

    result = router.call_tool(
        "search_candidate_safe_profiles",
        {"filters": {"position_query": "建模"}, "return_fields": ["name"], "limit": 5},
        identity,
    )

    assert result["candidates"][0]["name"] == "张三"
    assert audit.calls[-1]["tool_name"] == "search_candidate_safe_profiles"
    assert audit.calls[-1]["fields"] == ["name"]


def test_jsonrpc_handler_lists_and_calls_data_tools():
    router, _ = build_router()
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN")

    listed = handler.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, identity)
    called = handler.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "query_talent_pool_facts", "arguments": {"metrics": ["count"], "group_by": ["position_name"]}},
        },
        identity,
    )

    assert listed["result"]["tools"][0]["name"] == "search_candidate_safe_profiles"
    assert called["result"]["facts"]["count"] == 2


def test_removed_business_agent_tools_return_unknown_tool():
    router, _ = build_router()
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN")

    for tool_name in ["get_screening_policy", "analyze_talent_pool", "generate_recruitment_report"]:
        response = handler.handle(
            {"jsonrpc": "2.0", "id": tool_name, "method": "tools/call", "params": {"name": tool_name, "arguments": {}}},
            identity,
        )
        assert response["error"]["code"] == JsonRpcError.METHOD_NOT_FOUND


def test_unknown_tool_returns_jsonrpc_error_response():
    router, _ = build_router()
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN")

    response = handler.handle(
        {"jsonrpc": "2.0", "id": "bad", "method": "tools/call", "params": {"name": "missing", "arguments": {}}},
        identity,
    )

    assert response["id"] == "bad"
    assert response["error"]["code"] == JsonRpcError.METHOD_NOT_FOUND
    assert "Unknown MCP tool" in response["error"]["message"]


def test_tool_router_does_not_import_repository_layer():
    import hr_mcp.services.tool_router as tool_router_module

    source = inspect.getsource(tool_router_module)
    assert "repositories" not in source
    assert "mysql_repository" not in source
    assert "dump_repository" not in source


def test_jsonrpc_invalid_params_returns_invalid_params_error():
    router, _ = build_router()
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN")

    response = handler.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": []}, identity)
    assert response["error"]["code"] == JsonRpcError.INVALID_PARAMS

    response = handler.handle(
        {"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "query_talent_pool_facts", "arguments": "bad"}},
        identity,
    )
    assert response["error"]["code"] == JsonRpcError.INVALID_PARAMS


def test_router_denies_readonly_save_screening_result():
    router, _ = build_router()
    identity = IdentityContext(user_id=7, role="READONLY_VIEWER")

    with pytest.raises(PermissionError):
        router.call_tool(
            "save_screening_result",
            {"task_id": "task-1", "standard_ref": "standard_markdown/xiaoman.md", "recommended_candidates": []},
            identity,
        )
