"""MCP 工具注册服务。

该文件集中声明 HR MCP P0 暴露给 Claude Code Agent 的安全数据工具、入参 schema 和出参说明。
后端只提供候选人安全画像、候选人召回、聚合事实查询和推荐结果保存，不提供筛选推荐、问答、分析或报告生成。
候选人 filter schema 在这里收紧为白名单字段，防止工具调用层传入自由条件或未知参数。
"""

from copy import deepcopy
from typing import Any, Dict, List, Optional, Set, Tuple, Union


CANDIDATE_FILTER_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "position_query": {"type": "string"},
        "position_name": {"type": "string"},
        "position_id": {"type": "integer"},
        "name_query": {"type": "string"},
        "source_query": {"type": "string"},
        "source_id": {"type": "integer"},
        "proposed_department_id": {"type": "integer"},
        "hr_id": {"type": "integer"},
        "candidate_status": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
        "status": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
        "min_work_years": {"type": "integer", "minimum": 0},
        "max_work_years": {"type": "integer", "minimum": 0},
        "gender": {"type": "string"},
        "degree": {"type": "string"},
        "college_query": {"type": "string"},
        "major_query": {"type": "string"},
        "is_focused": {"type": "boolean"},
        "manual_import": {"type": "boolean"},
        "match_point_min": {"type": "integer", "minimum": 0},
        "skills_any": {"type": "array", "items": {"type": "string"}},
        "experience_keywords_any": {"type": "array", "items": {"type": "string"}},
        "candidate_pool": {"type": "string", "enum": ["active", "old_rejected", "recent_rejected", "hired", "joining"]},
        "rejected_before_days": {"type": "integer", "minimum": 1},
        "status_updated_before": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
        "status_updated_after": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
        "proposed_join_date_from": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
        "proposed_join_date_to": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
        "create_time_from": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
        "create_time_to": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
        "update_time_from": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
        "update_time_to": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
    },
}


class ToolRegistry:
    TOOL_DEFINITIONS: List[Dict[str, Any]] = [
        {
            "name": "search_candidate_safe_profiles",
            "description": "Search candidates and return field-policy-filtered safe profiles.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filters": CANDIDATE_FILTER_SCHEMA,
                    "return_fields": {"type": "array", "items": {"type": "string"}},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 300},
                    "cursor": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 300},
                },
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "candidates": {"type": "array"},
                    "total_count": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                    "next_cursor": {"type": ["string", "null"]},
                    "page_size": {"type": "integer"},
                },
            },
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
            "name": "query_hr_safe_sql",
            "description": "Execute a sandboxed read-only SELECT against approved HR safe views for open-ended factual questions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string"},
                    "purpose": {"type": "string"},
                    "access_reason": {"type": "string"},
                },
                "required": ["sql", "purpose"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "rows": {"type": "array"},
                    "row_count": {"type": "integer"},
                    "columns": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer"},
                    "view": {"type": "string"},
                    "privileged": {"type": "boolean"},
                },
            },
        },
        {
            "name": "describe_hr_safe_schema",
            "description": "Describe the safe SQL views and fields that Agent-authored SQL may query.",
            "input_schema": {"type": "object", "properties": {}},
            "output_schema": {"type": "object", "properties": {"views": {"type": "object"}}},
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

    def list_tools(self) -> List[Dict[str, Any]]:
        return deepcopy(self.TOOL_DEFINITIONS)

    def has_tool(self, tool_name: str) -> bool:
        return any(tool["name"] == tool_name for tool in self.TOOL_DEFINITIONS)
