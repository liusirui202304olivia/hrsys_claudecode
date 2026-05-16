import json
from pathlib import Path

from hr_mcp.models.context import IdentityContext
from hr_mcp.services.audit_trace_service import AuditTraceService
from hr_mcp.services.report_generation_service import ReportGenerationService
from hr_mcp.services.screening_policy_service import ScreeningPolicyService
from hr_mcp.services.screening_result_store import ScreeningResultStore
from hr_mcp.services.talent_analysis_service import TalentAnalysisService


class FakeRepository:
    def count_candidates(self, filters):
        return 2

    def position_distribution(self, filters):
        return [{"position_name": "芯片建模工程师", "count": 2}]

    def status_distribution(self, filters):
        return [{"status": "SCREEN_PROCESS", "count": 2}]

    def source_distribution(self, filters):
        return [{"source_name": "历史导入", "count": 2}]

    def search_candidates(self, filters, limit):
        return [
            {"candidate_id": 1, "name": "张三", "status": "SCREEN_PROCESS", "position_name": "芯片建模工程师"},
            {"candidate_id": 2, "name": "李四", "status": "SCREEN_PROCESS", "position_name": "芯片建模工程师"},
        ][:limit]


def test_screening_policy_service_matches_alias_and_loads_markdown(tmp_path: Path):
    policy_dir = tmp_path / "config" / "policies"
    markdown_dir = tmp_path / "standard_markdown"
    policy_dir.mkdir(parents=True)
    markdown_dir.mkdir(parents=True)
    (markdown_dir / "modeling.md").write_text("# 芯片建模工程师筛选标准\n## 必须满足\n- C++", encoding="utf-8")
    (policy_dir / "modeling.yml").write_text(
        "policy_id: chip_modeling_v1\n"
        "position_name: 芯片建模工程师\n"
        "version: '2026-05-16'\n"
        "markdown_file: modeling.md\n"
        "aliases:\n  - 芯片建模\n  - CPU建模\n",
        encoding="utf-8",
    )

    service = ScreeningPolicyService(policy_dir=policy_dir, markdown_dir=markdown_dir)
    policy = service.get_policy("CPU建模")

    assert policy["policy_id"] == "chip_modeling_v1"
    assert policy["position_name"] == "芯片建模工程师"
    assert "C++" in policy["content_markdown"]


def test_talent_analysis_service_outputs_pool_structure():
    service = TalentAnalysisService(FakeRepository())

    result = service.analyze_talent_pool(
        analysis_target="芯片建模候选人池",
        policy_id="chip_modeling_v1",
        filters={},
        dimensions=["position_name", "status", "source_name"],
        sample_limit=1,
    )

    assert result["summary_stats"]["total_candidates"] == 2
    assert result["sample_candidates"][0]["name"] == "张三"
    assert result["dimension_analysis"]["position_distribution"][0]["count"] == 2


def test_report_generation_service_includes_summary_risks_and_next_actions():
    report = ReportGenerationService().generate_recruitment_report(
        report_type="weekly_recruitment_analysis",
        policy={"position_name": "芯片建模工程师", "policy_id": "chip_modeling_v1"},
        analysis={
            "summary_stats": {"total_candidates": 2},
            "dimension_analysis": {"status_distribution": [{"status": "SCREEN_PROCESS", "count": 2}]},
            "observations": ["候选人集中在建模方向"],
            "sample_candidates": [{"name": "张三"}],
        },
        include_sections=["candidate_pool_overview", "quality_analysis", "risk_points", "next_actions"],
    )

    assert report["title"] == "芯片建模工程师候选人池分析报告"
    assert "风险" in report["content_markdown"]
    assert "下一步" in report["content_markdown"]


def test_result_store_and_audit_write_jsonl(tmp_path: Path):
    result_path = tmp_path / "results.jsonl"
    audit_path = tmp_path / "audit.jsonl"
    identity = IdentityContext(user_id=1, role="HR_ADMIN", request_id="req-1")

    saved = ScreeningResultStore(result_path).save_screening_result(
        screening_task_id="task-1",
        policy_id="chip_modeling_v1",
        recommended_candidates=[{"candidate_id": 1, "recommend_level": "强推荐"}],
        summary="推荐 1 人",
        identity=identity,
    )
    AuditTraceService(audit_path).record_tool_call(
        tool_name="save_screening_result",
        arguments={"screening_task_id": "task-1"},
        result_summary="saved",
        identity=identity,
        candidate_ids=[1],
        fields=["name"],
    )

    assert saved["screening_task_id"] == "task-1"
    assert json.loads(result_path.read_text(encoding="utf-8").splitlines()[0])["policy_id"] == "chip_modeling_v1"
    assert json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])["tool_name"] == "save_screening_result"


def test_talent_analysis_samples_use_safe_projection_without_contacts():
    from hr_mcp.security.field_policy import FieldPolicy
    from hr_mcp.services.candidate_safe_view_service import CandidateSafeViewService
    from hr_mcp.services.permission_service import PermissionService

    safe_view = CandidateSafeViewService(FieldPolicy(), PermissionService())
    class ContactRepository(FakeRepository):
        def search_candidates(self, filters, limit):
            return [
                {
                    "candidate_id": 1,
                    "name": "张三",
                    "status": "SCREEN_PROCESS",
                    "mobile": "13800000000",
                    "email": "z@example.com",
                }
            ][:limit]

    service = TalentAnalysisService(ContactRepository(), safe_view_service=safe_view)
    identity = IdentityContext(user_id=1, role="HR_ADMIN")

    result = service.analyze_talent_pool(
        analysis_target="芯片建模候选人池",
        policy_id="chip_modeling_v1",
        filters={},
        dimensions=[],
        sample_limit=1,
        identity=identity,
    )

    sample_text = json.dumps(result["sample_candidates"], ensure_ascii=False)
    assert "张三" in sample_text
    assert "mobile" not in sample_text
    assert "email" not in sample_text



def test_talent_analysis_applies_recruiter_scope_to_summary_and_samples():
    from hr_mcp.security.field_policy import FieldPolicy
    from hr_mcp.services.candidate_safe_view_service import CandidateSafeViewService
    from hr_mcp.services.permission_service import PermissionService

    class ScopedRepository:
        def search_candidates(self, filters, limit):
            return [
                {"candidate_id": 1, "name": "张三", "status": "SCREEN_PROCESS", "hr_id": 2, "position_name": "芯片建模工程师"},
                {"candidate_id": 2, "name": "李四", "status": "REJECTED", "hr_id": 3, "position_name": "应用软件开发工程师"},
            ][:limit]

        def count_candidates(self, filters):
            return 2

        def position_distribution(self, filters):
            return []

        def status_distribution(self, filters):
            return []

        def source_distribution(self, filters):
            return []

    safe_view = CandidateSafeViewService(FieldPolicy(), PermissionService())
    service = TalentAnalysisService(ScopedRepository(), safe_view_service=safe_view)

    result = service.analyze_talent_pool(
        analysis_target="范围测试",
        policy_id="policy-1",
        filters={},
        dimensions=["position_name", "status"],
        sample_limit=10,
        identity=IdentityContext(user_id=2, role="RECRUITER"),
    )

    assert result["summary_stats"]["total_candidates"] == 1
    assert result["dimension_analysis"]["position_distribution"] == [{"position_name": "芯片建模工程师", "count": 1}]
    assert result["sample_candidates"] == [{"hr_id": 2, "name": "张三", "status": "SCREEN_PROCESS"}]


def test_result_store_and_audit_sanitize_contact_fields(tmp_path: Path):
    result_path = tmp_path / "results.jsonl"
    audit_path = tmp_path / "audit.jsonl"
    identity = IdentityContext(user_id=1, role="HR_ADMIN", request_id="req-1")

    ScreeningResultStore(result_path).save_screening_result(
        screening_task_id="task-contacts",
        policy_id="policy-1",
        recommended_candidates=[{
            "candidate_id": 1,
            "name": "张三",
            "mobile": "13800000000",
            "email": "z@example.com",
            "phone": "010-1",
            "username": "zhangsan",
            "recommend_level": "强推荐",
        }],
        summary="推荐 1 人",
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
    assert "强推荐" in combined
