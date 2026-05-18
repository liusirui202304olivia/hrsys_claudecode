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
