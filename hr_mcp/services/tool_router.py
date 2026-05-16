"""MCP 工具路由服务。

该文件根据 MCP tool name 把调用分发给具体数据服务，并统一记录审计。
它不直接访问 repository，也不实现候选人筛选、推荐、问答、招聘分析或报告生成。
对于保存推荐结果等有写入副作用的工具，路由层会先执行工具级角色授权。
"""

from __future__ import annotations

from typing import Any

from hr_mcp.models.context import IdentityContext
from hr_mcp.services.tool_registry import ToolRegistry


class UnknownToolError(ValueError):
    pass


class InvalidToolArgumentsError(ValueError):
    pass


class ToolRouter:
    SAVE_ALLOWED_ROLES = {"HR_ADMIN", "RECRUITER"}

    def __init__(
        self,
        registry: ToolRegistry,
        retrieval_service,
        talent_query_service,
        result_store,
        audit_service,
    ):
        self.registry = registry
        self.retrieval_service = retrieval_service
        self.talent_query_service = talent_query_service
        self.result_store = result_store
        self.audit_service = audit_service

    def list_tools(self) -> list[dict[str, Any]]:
        return self.registry.list_tools()

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None, identity: IdentityContext) -> dict[str, Any]:
        arguments = arguments or {}
        if not isinstance(arguments, dict):
            raise InvalidToolArgumentsError("Tool arguments must be an object")
        if not self.registry.has_tool(tool_name):
            raise UnknownToolError(f"Unknown MCP tool: {tool_name}")

        if tool_name == "search_candidate_safe_profiles":
            candidates = self.retrieval_service.search_safe_profiles(
                filters=arguments.get("filters") or {},
                return_fields=arguments.get("return_fields"),
                limit=arguments.get("limit") or 50,
                identity=identity,
            )
            result = {"candidates": candidates}
        elif tool_name == "get_candidate_safe_detail_batch":
            result = self.retrieval_service.get_safe_detail_batch(
                candidate_ids=arguments.get("candidate_ids") or [],
                return_fields=arguments.get("return_fields"),
                identity=identity,
            )
        elif tool_name == "query_talent_pool_facts":
            result = {
                "facts": self.talent_query_service.query_facts(
                    metrics=arguments.get("metrics") or ["count"],
                    filters=arguments.get("filters") or {},
                    group_by=arguments.get("group_by") or [],
                    identity=identity,
                )
            }
        elif tool_name == "save_screening_result":
            self._assert_can_save(identity)
            result = {
                "saved": self.result_store.save_screening_result(
                    task_id=arguments.get("task_id", ""),
                    standard_ref=arguments.get("standard_ref", ""),
                    recommended_candidates=arguments.get("recommended_candidates") or [],
                    identity=identity,
                )
            }
        else:
            raise UnknownToolError(f"Unknown MCP tool: {tool_name}")

        self._audit(tool_name, arguments, result, identity)
        return result

    def _assert_can_save(self, identity: IdentityContext) -> None:
        if identity.role not in self.SAVE_ALLOWED_ROLES:
            raise PermissionError("save_screening_result requires HR_ADMIN or RECRUITER role")

    def _audit(self, tool_name: str, arguments: dict[str, Any], result: dict[str, Any], identity: IdentityContext) -> None:
        if not self.audit_service:
            return
        candidate_ids = self._candidate_ids(result)
        fields = arguments.get("return_fields") or []
        self.audit_service.record_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            result_summary=self._summary(result),
            identity=identity,
            candidate_ids=candidate_ids,
            fields=fields,
        )

    def _candidate_ids(self, result: dict[str, Any]) -> list[Any]:
        candidates = result.get("candidates") or result.get("saved", {}).get("recommended_candidates") or []
        ids: list[Any] = []
        for candidate in candidates:
            if isinstance(candidate, dict):
                candidate_id = candidate.get("candidate_id") or candidate.get("id")
                if candidate_id is not None:
                    ids.append(candidate_id)
        return ids

    def _summary(self, result: dict[str, Any]) -> str:
        if "candidates" in result:
            return f"returned {len(result.get('candidates') or [])} candidates"
        if "facts" in result:
            return "returned talent pool facts"
        if "saved" in result:
            return "saved screening result"
        return "ok"
