"""MCP 工具注册、路由与 JSON-RPC 测试。

该文件验证 4 个 MCP 安全数据工具清单、工具调用分发、审计记录、未知工具错误和 malformed params 的 JSON-RPC error code。
它还检查 ToolRouter 不 import repository，确保 MCP 层只做数据工具路由而不越层访问数据源。
保存推荐结果的角色授权也在这里做回归验证。
"""

import inspect

import pytest

from hr_mcp.mcp.jsonrpc import JsonRpcError, JsonRpcHandler
from hr_mcp.models.context import IdentityContext
from hr_mcp.security.field_policy import FieldAccessError
from hr_mcp.services.tool_registry import ToolRegistry
from hr_mcp.services.tool_router import ToolRouter


class FakeRetrievalService:
    def search_safe_profiles(self, filters, return_fields, page_size, identity, cursor=None):
        return {
            "candidates": [{"candidate_id": 1, "name": "张三"}],
            "total_count": 1,
            "has_more": False,
            "next_cursor": None,
            "page_size": page_size,
        }

    def get_safe_detail_batch(self, candidate_ids, return_fields, identity):
        return {"candidates": [{"candidate_id": candidate_ids[0], "name": "张三"}]}


class FieldDenyingRetrievalService(FakeRetrievalService):
    def search_safe_profiles(self, filters, return_fields, page_size, identity, cursor=None):
        raise FieldAccessError("Field hr_candidate.mobile requires privileged role")


class FakeTalentQueryService:
    def query_facts(self, metrics, filters, group_by, identity):
        return {"count": 2, "position_distribution": [{"position_name": "芯片建模", "count": 2}]}


class FakeResultStore:
    def __init__(self):
        self.calls = []

    def save_screening_result(self, task_id, standard_ref, recommended_candidates, identity):
        self.calls.append({
            "task_id": task_id,
            "standard_ref": standard_ref,
            "recommended_candidates": recommended_candidates,
        })
        return {"task_id": task_id, "standard_ref": standard_ref, "recommended_candidates": recommended_candidates, "saved": True}


class FakeAudit:
    def __init__(self):
        self.calls = []

    def record_tool_call(self, tool_name, arguments, result_summary, identity, candidate_ids=None, fields=None):
        self.calls.append({"tool_name": tool_name, "arguments": arguments, "fields": fields or [], "status": "success"})
        return self.calls[-1]

    def record_tool_failure(self, tool_name, arguments, identity, error_type, error_message, fields=None):
        self.calls.append({
            "tool_name": tool_name,
            "arguments": arguments,
            "fields": fields or [],
            "status": "failure",
            "error_type": error_type,
            "error_message": error_message,
            "request_id": identity.request_id,
        })
        return self.calls[-1]


def build_router():
    audit = FakeAudit()
    result_store = FakeResultStore()
    router = ToolRouter(
        registry=ToolRegistry(),
        retrieval_service=FakeRetrievalService(),
        talent_query_service=FakeTalentQueryService(),
        result_store=result_store,
        audit_service=audit,
    )
    return router, audit, result_store


def build_router_with_retrieval(retrieval_service):
    audit = FakeAudit()
    result_store = FakeResultStore()
    router = ToolRouter(
        registry=ToolRegistry(),
        retrieval_service=retrieval_service,
        talent_query_service=FakeTalentQueryService(),
        result_store=result_store,
        audit_service=audit,
    )
    return router, audit, result_store


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
    router, audit, _ = build_router()
    identity = IdentityContext(user_id=7, role="HR_ADMIN")

    result = router.call_tool(
        "search_candidate_safe_profiles",
        {"filters": {"position_query": "建模"}, "return_fields": ["name"], "limit": 5},
        identity,
    )

    assert result["candidates"][0]["name"] == "张三"
    assert result["total_count"] == 1
    assert audit.calls[-1]["tool_name"] == "search_candidate_safe_profiles"
    assert audit.calls[-1]["fields"] == ["name"]


def test_jsonrpc_handler_lists_and_calls_data_tools():
    router, _, _ = build_router()
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
    router, _, _ = build_router()
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN")

    for tool_name in ["get_screening_policy", "analyze_talent_pool", "generate_recruitment_report"]:
        response = handler.handle(
            {"jsonrpc": "2.0", "id": tool_name, "method": "tools/call", "params": {"name": tool_name, "arguments": {}}},
            identity,
        )
        assert response["error"]["code"] == JsonRpcError.METHOD_NOT_FOUND


def test_unknown_tool_returns_jsonrpc_error_response():
    router, _, _ = build_router()
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
    router, _, _ = build_router()
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN")

    response = handler.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": []}, identity)
    assert response["error"]["code"] == JsonRpcError.INVALID_PARAMS


def test_search_invalid_page_size_returns_invalid_params_before_calling_service():
    class FailingIfCalledRetrievalService(FakeRetrievalService):
        def search_safe_profiles(self, filters, return_fields, page_size, identity, cursor=None):
            raise AssertionError("retrieval service should not be called for invalid page_size")

    router, audit, _ = build_router_with_retrieval(FailingIfCalledRetrievalService())
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN", request_id="req-page-size")

    response = handler.handle(
        {
            "jsonrpc": "2.0",
            "id": "bad-page-size",
            "method": "tools/call",
            "params": {
                "name": "search_candidate_safe_profiles",
                "arguments": {"page_size": 301},
            },
        },
        identity,
    )

    assert response["error"]["code"] == JsonRpcError.INVALID_PARAMS
    assert audit.calls[-1]["status"] == "failure"
    assert audit.calls[-1]["error_type"] == "InvalidToolArgumentsError"


@pytest.mark.parametrize("arguments", [{"page_size": True}, {"limit": False}])
def test_search_boolean_page_size_returns_invalid_params_before_calling_service(arguments):
    class FailingIfCalledRetrievalService(FakeRetrievalService):
        def search_safe_profiles(self, filters, return_fields, page_size, identity, cursor=None):
            raise AssertionError("retrieval service should not be called for boolean page_size")

    router, audit, _ = build_router_with_retrieval(FailingIfCalledRetrievalService())
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN", request_id="req-bool-page-size")

    response = handler.handle(
        {
            "jsonrpc": "2.0",
            "id": "bad-bool-page-size",
            "method": "tools/call",
            "params": {
                "name": "search_candidate_safe_profiles",
                "arguments": arguments,
            },
        },
        identity,
    )

    assert response["error"]["code"] == JsonRpcError.INVALID_PARAMS
    assert audit.calls[-1]["status"] == "failure"
    assert audit.calls[-1]["error_type"] == "InvalidToolArgumentsError"


@pytest.mark.parametrize(
    "filters",
    [
        {"candidate_pool": "bad"},
        {"candidate_pool": "active", "status": ["SCREEN_PROCESS"]},
        {"candidate_pool": "old_rejected", "rejected_before_days": True},
        {"candidate_pool": "old_rejected", "rejected_before_days": 0},
        {"candidate_pool": "old_rejected", "rejected_before_days": -1},
        {"candidate_pool": "old_rejected", "rejected_before_days": "abc"},
        {"status_updated_before": "2026/01/01"},
        {"status_updated_after": "not-a-date"},
        {"free_sql": "status = 'REJECTED'"},
    ],
)
def test_search_invalid_candidate_pool_filters_return_invalid_params_before_calling_service(filters):
    class FailingIfCalledRetrievalService(FakeRetrievalService):
        def search_safe_profiles(self, filters, return_fields, page_size, identity, cursor=None):
            raise AssertionError("retrieval service should not be called for invalid filters")

    router, audit, _ = build_router_with_retrieval(FailingIfCalledRetrievalService())
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN", request_id="req-filter")

    response = handler.handle(
        {
            "jsonrpc": "2.0",
            "id": "bad-filter",
            "method": "tools/call",
            "params": {
                "name": "search_candidate_safe_profiles",
                "arguments": {"filters": filters},
            },
        },
        identity,
    )

    assert response["error"]["code"] == JsonRpcError.INVALID_PARAMS
    assert audit.calls[-1]["status"] == "failure"
    assert audit.calls[-1]["error_type"] == "InvalidToolArgumentsError"


def test_query_invalid_candidate_pool_filters_return_invalid_params_before_calling_service():
    class FailingTalentQueryService(FakeTalentQueryService):
        def query_facts(self, metrics, filters, group_by, identity):
            raise AssertionError("talent query service should not be called for invalid filters")

    audit = FakeAudit()
    router = ToolRouter(
        registry=ToolRegistry(),
        retrieval_service=FakeRetrievalService(),
        talent_query_service=FailingTalentQueryService(),
        result_store=FakeResultStore(),
        audit_service=audit,
    )
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN", request_id="req-query-filter")

    response = handler.handle(
        {
            "jsonrpc": "2.0",
            "id": "bad-query-filter",
            "method": "tools/call",
            "params": {
                "name": "query_talent_pool_facts",
                "arguments": {"filters": {"candidate_pool": "active", "status": ["SCREEN_PROCESS"]}},
            },
        },
        identity,
    )

    assert response["error"]["code"] == JsonRpcError.INVALID_PARAMS
    assert audit.calls[-1]["status"] == "failure"
    assert audit.calls[-1]["tool_name"] == "query_talent_pool_facts"


def test_detail_batch_too_many_ids_returns_invalid_params_before_calling_service():
    class FailingIfCalledRetrievalService(FakeRetrievalService):
        def get_safe_detail_batch(self, candidate_ids, return_fields, identity):
            raise AssertionError("retrieval service should not be called for too many candidate_ids")

    router, audit, _ = build_router_with_retrieval(FailingIfCalledRetrievalService())
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN", request_id="req-detail-size")

    response = handler.handle(
        {
            "jsonrpc": "2.0",
            "id": "bad-detail-size",
            "method": "tools/call",
            "params": {
                "name": "get_candidate_safe_detail_batch",
                "arguments": {"candidate_ids": list(range(51))},
            },
        },
        identity,
    )

    assert response["error"]["code"] == JsonRpcError.INVALID_PARAMS
    assert audit.calls[-1]["status"] == "failure"
    assert audit.calls[-1]["error_type"] == "InvalidToolArgumentsError"

    response = handler.handle(
        {"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "query_talent_pool_facts", "arguments": "bad"}},
        identity,
    )
    assert response["error"]["code"] == JsonRpcError.INVALID_PARAMS


def test_router_denies_readonly_save_screening_result():
    router, _, _ = build_router()
    identity = IdentityContext(user_id=7, role="READONLY_VIEWER")

    with pytest.raises(PermissionError):
        router.call_tool(
            "save_screening_result",
            {"task_id": "task-1", "standard_ref": "standard_markdown/xiaoman.md", "recommended_candidates": []},
            identity,
        )


@pytest.mark.parametrize("role", ["HR_ADMIN", "RECRUITER", "DEPARTMENT_MANAGER", "INTERVIEWER"])
def test_router_allows_business_roles_to_save_screening_result(role):
    router, _, result_store = build_router()
    identity = IdentityContext(user_id=7, role=role)

    result = router.call_tool(
        "save_screening_result",
        {
            "task_id": "task-1",
            "standard_ref": "standard_markdown/xiaoman.md",
            "recommended_candidates": [
                {
                    "candidate_id": 1,
                    "recommend_reason": "安全画像证据匹配目标岗位标准，来源岗位不同已作为风险说明。",
                    "risk_points": ["跨岗位推荐，需要面试验证目标岗位适配度"],
                }
            ],
        },
        identity,
    )

    assert result["saved"]["saved"] is True
    assert result_store.calls[-1]["recommended_candidates"][0]["candidate_id"] == 1


def test_jsonrpc_maps_permission_error_to_forbidden_and_audits_failure():
    router, audit, _ = build_router()
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="READONLY_VIEWER", request_id="req-deny")

    response = handler.handle(
        {
            "jsonrpc": "2.0",
            "id": "deny",
            "method": "tools/call",
            "params": {
                "name": "save_screening_result",
                "arguments": {
                    "task_id": "task-1",
                    "standard_ref": "standard_markdown/xiaoman.md",
                    "recommended_candidates": [],
                },
            },
        },
        identity,
    )

    assert response["error"]["code"] == JsonRpcError.FORBIDDEN
    assert audit.calls[-1]["status"] == "failure"
    assert audit.calls[-1]["tool_name"] == "save_screening_result"
    assert audit.calls[-1]["error_type"] == "PermissionError"
    assert audit.calls[-1]["request_id"] == "req-deny"


def test_invalid_save_arguments_return_invalid_params_and_do_not_write_result():
    router, audit, result_store = build_router()
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN", request_id="req-invalid")

    response = handler.handle(
        {
            "jsonrpc": "2.0",
            "id": "invalid-save",
            "method": "tools/call",
            "params": {
                "name": "save_screening_result",
                "arguments": {
                    "task_id": "",
                    "standard_ref": "standard_markdown/xiaoman.md",
                    "recommended_candidates": [{"candidate_id": 1, "risk_points": []}],
                },
            },
        },
        identity,
    )

    assert response["error"]["code"] == JsonRpcError.INVALID_PARAMS
    assert result_store.calls == []
    assert audit.calls[-1]["status"] == "failure"
    assert audit.calls[-1]["error_type"] == "InvalidToolArgumentsError"


def test_jsonrpc_invalid_arguments_type_records_failed_audit():
    router, audit, _ = build_router()
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN", request_id="req-bad-args")

    response = handler.handle(
        {
            "jsonrpc": "2.0",
            "id": "bad-args",
            "method": "tools/call",
            "params": {"name": "query_talent_pool_facts", "arguments": "bad"},
        },
        identity,
    )

    assert response["error"]["code"] == JsonRpcError.INVALID_PARAMS
    assert audit.calls[-1]["status"] == "failure"
    assert audit.calls[-1]["tool_name"] == "query_talent_pool_facts"
    assert audit.calls[-1]["error_type"] == "InvalidParamsError"


def test_jsonrpc_rejects_falsy_non_object_arguments_and_does_not_write_result():
    router, audit, result_store = build_router()
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="HR_ADMIN", request_id="req-list-args")

    response = handler.handle(
        {
            "jsonrpc": "2.0",
            "id": "bad-list-args",
            "method": "tools/call",
            "params": {"name": "save_screening_result", "arguments": []},
        },
        identity,
    )

    assert response["error"]["code"] == JsonRpcError.INVALID_PARAMS
    assert result_store.calls == []
    assert audit.calls[-1]["status"] == "failure"
    assert audit.calls[-1]["tool_name"] == "save_screening_result"
    assert audit.calls[-1]["error_type"] == "InvalidParamsError"


def test_jsonrpc_maps_field_access_error_to_forbidden_and_audits_requested_fields():
    router, audit, _ = build_router_with_retrieval(FieldDenyingRetrievalService())
    handler = JsonRpcHandler(router)
    identity = IdentityContext(user_id=7, role="RECRUITER", request_id="req-field-deny")

    response = handler.handle(
        {
            "jsonrpc": "2.0",
            "id": "field-deny",
            "method": "tools/call",
            "params": {
                "name": "search_candidate_safe_profiles",
                "arguments": {"return_fields": ["name", "mobile"], "limit": 5},
            },
        },
        identity,
    )

    assert response["error"]["code"] == JsonRpcError.FORBIDDEN
    assert audit.calls[-1]["status"] == "failure"
    assert audit.calls[-1]["tool_name"] == "search_candidate_safe_profiles"
    assert audit.calls[-1]["fields"] == ["name", "mobile"]
    assert audit.calls[-1]["error_type"] == "FieldAccessError"
