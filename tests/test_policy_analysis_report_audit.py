"""推荐结果存储与审计测试。

该文件验证后端只保存 Claude Code Agent 已生成的推荐结果，不生成筛选推荐、分析结论或报告内容。
测试覆盖 task_id、standard_ref、candidate_id、推荐理由和风险点的保存格式。
同时检查推荐结果和审计日志会清洗联系方式等敏感字段。
"""

import json
from pathlib import Path

from hr_mcp.models.context import IdentityContext
from hr_mcp.services.audit_trace_service import AuditTraceService
from hr_mcp.services.screening_result_store import ScreeningResultStore


def test_result_store_and_audit_write_confirmed_schema_jsonl(tmp_path: Path):
    result_path = tmp_path / "results.jsonl"
    audit_path = tmp_path / "audit.jsonl"
    identity = IdentityContext(user_id=1, role="HR_ADMIN", request_id="req-1")

    saved = ScreeningResultStore(result_path).save_screening_result(
        task_id="task-1",
        standard_ref="standard_markdown/xiaoman.md",
        recommended_candidates=[{"candidate_id": 1, "recommend_reason": "项目经历匹配", "risk_points": ["需确认主导性"]}],
        identity=identity,
    )
    AuditTraceService(audit_path).record_tool_call(
        tool_name="save_screening_result",
        arguments={"task_id": "task-1", "standard_ref": "standard_markdown/xiaoman.md"},
        result_summary="saved",
        identity=identity,
        candidate_ids=[1],
        fields=["name"],
    )

    assert saved["task_id"] == "task-1"
    assert saved["standard_ref"] == "standard_markdown/xiaoman.md"
    assert saved["recommended_candidates"] == [
        {"candidate_id": 1, "recommend_reason": "项目经历匹配", "risk_points": ["需确认主导性"]}
    ]
    assert json.loads(result_path.read_text(encoding="utf-8").splitlines()[0])["standard_ref"] == "standard_markdown/xiaoman.md"
    assert json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])["tool_name"] == "save_screening_result"


def test_result_store_and_audit_sanitize_contact_fields(tmp_path: Path):
    result_path = tmp_path / "results.jsonl"
    audit_path = tmp_path / "audit.jsonl"
    identity = IdentityContext(user_id=1, role="HR_ADMIN", request_id="req-1")

    ScreeningResultStore(result_path).save_screening_result(
        task_id="task-contacts",
        standard_ref="standard_markdown/yihai.md",
        recommended_candidates=[{
            "candidate_id": 1,
            "name": "张三",
            "mobile": "13800000000",
            "email": "z@example.com",
            "phone": "010-1",
            "username": "zhangsan",
            "recommend_reason": "标准匹配",
            "risk_points": ["需核实经历"],
        }],
        identity=identity,
    )
    AuditTraceService(audit_path).record_tool_call(
        tool_name="save_screening_result",
        arguments={"recommended_candidates": [{"mobile": "13800000000", "email": "z@example.com"}]},
        result_summary="saved",
        identity=identity,
    )

    combined = result_path.read_text(encoding="utf-8") + audit_path.read_text(encoding="utf-8")
    assert "13800000000" not in combined
    assert "z@example.com" not in combined
    assert "username" not in combined
    assert "标准匹配" in combined
    assert "需核实经历" in combined
