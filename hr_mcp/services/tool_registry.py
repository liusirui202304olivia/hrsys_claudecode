"""MCP 工具注册服务。

该文件集中声明 HR MCP P0 暴露给 Claude Code Agent 的 4 个安全数据工具、入参 schema 和出参说明。
后端只提供候选人安全画像、候选人召回、聚合事实查询和推荐结果保存，不提供筛选推荐、问答、分析或报告生成。
候选人 filter schema 在这里收紧为白名单字段，防止工具调用层传入自由条件或未知参数。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


CANDIDATE_FILTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "position_query": {"type": "string"},
        "position_name": {"type": "string"},
        "position_id": {"type": "integer"},
        "candidate_status": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
        "status": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
        "min_work_years": {"type": "integer", "minimum": 0},
        "skills_any": {"type": "array", "items": {"type": "string"}},
        "experience_keywords_any": {"type": "array", "items": {"type": "string"}},
    },
}


class ToolRegistry:
    TOOL_DEFINITIONS: list[dict[str, Any]] = [
        {
            "name": "search_candidate_safe_profiles",
            "description": "Search candidates and return field-policy-filtered safe profiles.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filters": CANDIDATE_FILTER_SCHEMA,
                    "return_fields": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer", "minimum": 0, "maximum": 300},
                },
            },
            "output_schema": {"type": "object", "properties": {"candidates": {"type": "array"}}},
        },
        {
            "name": "get_candidate_safe_detail_batch",
            "description": "Read candidate details in batches capped by service policy.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "candidate_ids": {"type": "array", "items": {"type": ["integer", "string"]}},
                    "return_fields": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["candidate_ids"],
            },
            "output_schema": {"type": "object", "properties": {"candidates": {"type": "array"}}},
        },
        {
            "name": "query_talent_pool_facts",
            "description": "Run controlled fact queries and aggregate distributions over the talent pool.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "metrics": {"type": "array", "items": {"type": "string"}},
                    "filters": CANDIDATE_FILTER_SCHEMA,
                    "group_by": {"type": "array", "items": {"type": "string"}},
                },
            },
            "output_schema": {"type": "object", "properties": {"facts": {"type": "object"}}},
        },
        {
            "name": "save_screening_result",
            "description": "Persist Agent-generated screening recommendations and audit the save.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "standard_ref": {"type": "string"},
                    "recommended_candidates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "candidate_id": {"type": ["integer", "string"]},
                                "recommend_reason": {"type": "string"},
                                "risk_points": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["candidate_id", "recommend_reason", "risk_points"],
                        },
                    },
                },
                "required": ["task_id", "standard_ref", "recommended_candidates"],
            },
            "output_schema": {"type": "object", "properties": {"saved": {"type": "object"}}},
        },
    ]

    def list_tools(self) -> list[dict[str, Any]]:
        return deepcopy(self.TOOL_DEFINITIONS)

    def has_tool(self, tool_name: str) -> bool:
        return any(tool["name"] == tool_name for tool in self.TOOL_DEFINITIONS)
