"""MCP 工具路由服务。

该文件根据 MCP tool name 把调用分发给具体数据服务，并统一记录审计。
它不直接访问 repository，也不实现候选人筛选、推荐、问答、招聘分析或报告生成。
对于保存推荐结果等有写入副作用的工具，路由层会先执行工具级角色授权。
"""

from typing import Any, Dict, List, Optional, Set, Tuple, Union

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

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.registry.list_tools()

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]], identity: IdentityContext) -> Dict[str, Any]:
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            exc = InvalidToolArgumentsError("Tool arguments must be an object")
            self.record_failed_call(tool_name, {}, identity, exc)
            raise exc
        try:
            if not self.registry.has_tool(tool_name):
                raise UnknownToolError(f"Unknown MCP tool: {tool_name}")
            self._validate_arguments(tool_name, arguments)

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
        except Exception as exc:
            self.record_failed_call(tool_name, arguments, identity, exc)
            raise

        self._audit(tool_name, arguments, result, identity)
        return result

    def record_failed_call(self, tool_name: str, arguments: Dict[str, Any], identity: IdentityContext, exc: Exception) -> None:
        if not self.audit_service:
            return
        fields = arguments.get("return_fields") if isinstance(arguments, dict) else []
        self.audit_service.record_tool_failure(
            tool_name=tool_name or "<invalid>",
            arguments=arguments if isinstance(arguments, dict) else {},
            identity=identity,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            fields=fields if isinstance(fields, list) else [],
        )

    def _assert_can_save(self, identity: IdentityContext) -> None:
        if identity.role not in self.SAVE_ALLOWED_ROLES:
            raise PermissionError("save_screening_result requires HR_ADMIN or RECRUITER role")

    def _validate_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        if tool_name == "search_candidate_safe_profiles":
            self._validate_optional_dict(arguments, "filters")
            self._validate_optional_string_list(arguments, "return_fields")
            if "limit" in arguments and not isinstance(arguments["limit"], int):
                raise InvalidToolArgumentsError("search_candidate_safe_profiles.limit must be an integer")
        elif tool_name == "get_candidate_safe_detail_batch":
            candidate_ids = arguments.get("candidate_ids")
            if not isinstance(candidate_ids, list):
                raise InvalidToolArgumentsError("get_candidate_safe_detail_batch.candidate_ids must be an array")
            self._validate_optional_string_list(arguments, "return_fields")
        elif tool_name == "query_talent_pool_facts":
            self._validate_optional_dict(arguments, "filters")
            self._validate_optional_string_list(arguments, "metrics")
            self._validate_optional_string_list(arguments, "group_by")
        elif tool_name == "save_screening_result":
            if not isinstance(arguments.get("task_id"), str) or not arguments.get("task_id").strip():
                raise InvalidToolArgumentsError("save_screening_result.task_id must be a non-empty string")
            if not isinstance(arguments.get("standard_ref"), str) or not arguments.get("standard_ref").strip():
                raise InvalidToolArgumentsError("save_screening_result.standard_ref must be a non-empty string")
            recommended_candidates = arguments.get("recommended_candidates")
            if not isinstance(recommended_candidates, list):
                raise InvalidToolArgumentsError("save_screening_result.recommended_candidates must be an array")
            for index, candidate in enumerate(recommended_candidates):
                if not isinstance(candidate, dict):
                    raise InvalidToolArgumentsError(f"recommended_candidates[{index}] must be an object")
                if candidate.get("candidate_id") in (None, ""):
                    raise InvalidToolArgumentsError(f"recommended_candidates[{index}].candidate_id is required")
                if not isinstance(candidate.get("recommend_reason"), str) or not candidate.get("recommend_reason").strip():
                    raise InvalidToolArgumentsError(f"recommended_candidates[{index}].recommend_reason must be a non-empty string")
                if not isinstance(candidate.get("risk_points"), list) or not all(isinstance(item, str) for item in candidate.get("risk_points")):
                    raise InvalidToolArgumentsError(f"recommended_candidates[{index}].risk_points must be an array of strings")

    def _validate_optional_dict(self, arguments: Dict[str, Any], key: str) -> None:
        if key in arguments and not isinstance(arguments[key], dict):
            raise InvalidToolArgumentsError(f"{key} must be an object")

    def _validate_optional_string_list(self, arguments: Dict[str, Any], key: str) -> None:
        if key in arguments and not (isinstance(arguments[key], list) and all(isinstance(item, str) for item in arguments[key])):
            raise InvalidToolArgumentsError(f"{key} must be an array of strings")

    def _audit(self, tool_name: str, arguments: Dict[str, Any], result: Dict[str, Any], identity: IdentityContext) -> None:
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

    def _candidate_ids(self, result: Dict[str, Any]) -> List[Any]:
        candidates = result.get("candidates") or result.get("saved", {}).get("recommended_candidates") or []
        ids: List[Any] = []
        for candidate in candidates:
            if isinstance(candidate, dict):
                candidate_id = candidate.get("candidate_id") or candidate.get("id")
                if candidate_id is not None:
                    ids.append(candidate_id)
        return ids

    def _summary(self, result: Dict[str, Any]) -> str:
        if "candidates" in result:
            return f"returned {len(result.get('candidates') or [])} candidates"
        if "facts" in result:
            return "returned talent pool facts"
        if "saved" in result:
            return "saved screening result"
        return "ok"
