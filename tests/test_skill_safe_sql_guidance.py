"""Skill guidance tests for open-ended safe SQL usage.

These tests ensure Claude Code Skills can choose safe SQL for broad factual
questions while preserving the architecture boundary: Skill performs business
reasoning, MCP/API enforces data security.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_qa_skill_defines_open_ended_safe_sql_and_join_date_questions():
    content = _read("skills/hr-talent-database-qa/SKILL.md")

    required_rules = [
        "query_hr_safe_sql",
        "describe_hr_safe_schema",
        "安全 SQL",
        "准备入职",
        "proposed_join_date",
        "排除 `REJECTED`、`HIRED`",
        "看什么数据由 Agent 判断",
        "业务判断由 Skill 指导",
        "安全边界由 MCP/API 后端控制",
    ]

    for rule in required_rules:
        assert rule in content


def test_screening_analysis_report_skills_allow_safe_sql_without_backend_business_reasoning():
    for relative_path in [
        "skills/hr-candidate-screening/SKILL.md",
        "skills/hr-talent-analysis/SKILL.md",
        "skills/hr-recruitment-report/SKILL.md",
    ]:
        content = _read(relative_path)
        assert "query_hr_safe_sql" in content
        assert "安全 SQL" in content
        assert "业务判断" in content


def test_skills_document_interview_and_screen_evaluation_safe_views():
    required_terms = [
        "v_candidate_interview_safe",
        "v_candidate_interview_evaluate_safe",
        "v_candidate_interview_question_safe",
        "v_candidate_screen_evaluate_safe",
        "hr_interview_evaluate",
        "hr_screen_evaluate",
    ]

    for relative_path in [
        "skills/hr-talent-database-qa/SKILL.md",
        "skills/hr-candidate-screening/SKILL.md",
        "skills/hr-talent-analysis/SKILL.md",
        "skills/hr-recruitment-report/SKILL.md",
    ]:
        content = _read(relative_path)
        for term in required_terms:
            assert term in content


def test_skill_interview_evaluation_guidance_is_chinese_first():
    forbidden_english_fragments = [
        "Interview And Screening Evaluation Safe SQL",
        "Approved evaluation safe views",
        "Never query raw tables",
        "When screening or ranking needs",
        "When analysis needs",
    ]

    for relative_path in [
        "skills/hr-talent-database-qa/SKILL.md",
        "skills/hr-candidate-screening/SKILL.md",
        "skills/hr-talent-analysis/SKILL.md",
        "skills/hr-recruitment-report/SKILL.md",
    ]:
        content = _read(relative_path)
        for fragment in forbidden_english_fragments:
            assert fragment not in content

        assert "面试" in content
        assert "初筛" in content
        assert "禁止查询原表" in content


def test_entry_skill_lists_current_mcp_tools_and_safe_views():
    content = _read("skills/hr-talent-intelligence/SKILL.md")

    for tool_name in [
        "search_candidate_safe_profiles",
        "get_candidate_safe_detail_batch",
        "query_talent_pool_facts",
        "query_hr_safe_sql",
        "describe_hr_safe_schema",
        "save_screening_result",
    ]:
        assert tool_name in content

    for safe_view in [
        "v_candidate_agent_safe",
        "v_candidate_agent_privileged",
        "v_candidate_interview_safe",
        "v_candidate_interview_evaluate_safe",
        "v_candidate_interview_question_safe",
        "v_candidate_screen_evaluate_safe",
    ]:
        assert safe_view in content
