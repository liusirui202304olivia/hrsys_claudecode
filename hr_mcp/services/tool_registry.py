from __future__ import annotations

from copy import deepcopy
from typing import Any


class ToolRegistry:
    TOOL_DEFINITIONS: list[dict[str, Any]] = [
        {
            "name": "get_screening_policy",
            "description": "Load Markdown screening policy by position name or alias.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "position_query": {"type": "string"},
                    "department_hint": {"type": "string"},
                },
                "required": ["position_query"],
            },
            "output_schema": {"type": "object", "properties": {"policy": {"type": "object"}}},
        },
        {
            "name": "search_candidate_safe_profiles",
            "description": "Search candidates and return field-policy-filtered safe profiles.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filters": {"type": "object"},
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
                    "filters": {"type": "object"},
                    "group_by": {"type": "array", "items": {"type": "string"}},
                },
            },
            "output_schema": {"type": "object", "properties": {"facts": {"type": "object"}}},
        },
        {
            "name": "analyze_talent_pool",
            "description": "Generate structured recruiting analysis for a candidate pool.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "analysis_target": {"type": "string"},
                    "policy_id": {"type": "string"},
                    "filters": {"type": "object"},
                    "dimensions": {"type": "array", "items": {"type": "string"}},
                    "sample_limit": {"type": "integer", "minimum": 0, "maximum": 30},
                },
            },
            "output_schema": {"type": "object", "properties": {"analysis": {"type": "object"}}},
        },
        {
            "name": "generate_recruitment_report",
            "description": "Build a structured Markdown recruitment report from policy and analysis input.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "report_type": {"type": "string"},
                    "policy": {"type": "object"},
                    "analysis": {"type": "object"},
                    "include_sections": {"type": "array", "items": {"type": "string"}},
                },
            },
            "output_schema": {"type": "object", "properties": {"report": {"type": "object"}}},
        },
        {
            "name": "save_screening_result",
            "description": "Persist recommended candidates for a screening task and audit the save.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "screening_task_id": {"type": "string"},
                    "policy_id": {"type": "string"},
                    "recommended_candidates": {"type": "array", "items": {"type": "object"}},
                    "summary": {"type": "string"},
                },
                "required": ["screening_task_id", "policy_id", "recommended_candidates"],
            },
            "output_schema": {"type": "object", "properties": {"saved": {"type": "object"}}},
        },
    ]

    def list_tools(self) -> list[dict[str, Any]]:
        return deepcopy(self.TOOL_DEFINITIONS)

    def has_tool(self, tool_name: str) -> bool:
        return any(tool["name"] == tool_name for tool in self.TOOL_DEFINITIONS)
