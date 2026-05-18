"""
Validate the project-local Claude Code Skill layout for the HR talent
intelligence workflow.

The MCP/API backend in this repository is a secure data service. The business
reasoning layer lives in project-local Claude Code Skills, so this test protects
the intended split: one entry Skill plus four first-level business task Skills.
It also prevents a regression back to one oversized Skill or tool-action Skills.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_project_skills_are_first_level_business_task_skills() -> None:
    expected_skill_dirs = {
        "hr-talent-intelligence",
        "hr-candidate-screening",
        "hr-talent-database-qa",
        "hr-talent-analysis",
        "hr-recruitment-report",
    }

    actual_skill_dirs = {
        skill_file.parent.name for skill_file in SKILLS.glob("*/SKILL.md")
    }

    assert expected_skill_dirs.issubset(actual_skill_dirs)
    assert not (SKILLS / "hr_recruitment").exists()
    assert not (SKILLS / "hr_talent_intelligence").exists()


def test_entry_skill_routes_to_business_task_skills() -> None:
    content = _read("skills/hr-talent-intelligence/SKILL.md")

    for skill_path in [
        "skills/hr-candidate-screening/SKILL.md",
        "skills/hr-talent-database-qa/SKILL.md",
        "skills/hr-talent-analysis/SKILL.md",
        "skills/hr-recruitment-report/SKILL.md",
    ]:
        assert skill_path in content

    forbidden_tool_action_skills = [
        "读取岗位标准 Skill",
        "读取候选人 Skill",
        "统计数量 Skill",
        "保存结果 Skill",
    ]
    all_skill_text = "\n".join(
        path.read_text(encoding="utf-8") for path in SKILLS.glob("*/SKILL.md")
    )
    for forbidden in forbidden_tool_action_skills:
        assert forbidden not in all_skill_text


def test_skills_keep_backend_as_safe_data_service() -> None:
    all_skill_text = "\n".join(
        path.read_text(encoding="utf-8") for path in SKILLS.glob("*/SKILL.md")
    )

    for tool_name in [
        "search_candidate_safe_profiles",
        "get_candidate_safe_detail_batch",
        "query_talent_pool_facts",
        "query_hr_safe_sql",
        "describe_hr_safe_schema",
        "save_screening_result",
    ]:
        assert tool_name in all_skill_text

    for removed_backend_tool in [
        "get_screening_policy",
        "analyze_talent_pool",
        "generate_recruitment_report",
    ]:
        assert removed_backend_tool not in all_skill_text


def test_recruitment_report_skill_targets_hr_ppt_style_reports() -> None:
    content = _read("skills/hr-recruitment-report/SKILL.md")

    required_report_elements = [
        "招聘漏斗",
        "转化率",
        "流失原因",
        "关键指标卡",
        "PPT",
        "图表建议",
        "行动建议",
        "简历投递",
        "初筛合格",
        "成功入职",
    ]

    for element in required_report_elements:
        assert element in content

    assert "不要只输出通用 Markdown 章节" in content


def test_screening_skill_defines_candidate_pool_recommendation_strategy() -> None:
    content = _read("skills/hr-candidate-screening/SKILL.md")

    required_rules = [
        "candidate_pool",
        "active",
        "old_rejected",
        "recent_rejected",
        "rejected_before_days",
        "180",
        "update_time",
        "状态更新时间",
        "被拒时间",
        "优先推荐",
        "补充考虑",
        "暂不推荐",
    ]

    for rule in required_rules:
        assert rule in content


def test_screening_skill_defines_full_pool_cross_position_strategy() -> None:
    content = _read("skills/hr-candidate-screening/SKILL.md")

    required_rules = [
        "全库安全画像",
        "不要默认用目标岗位名做 position_query 窄筛",
        "candidate.position_id",
        "candidate.position_name",
        "来源岗位",
        "目标岗位",
        "跨岗位推荐",
        "关联岗位",
        "近似岗位",
        "skills_any",
        "experience_keywords_any",
    ]

    for rule in required_rules:
        assert rule in content


def test_screening_skill_includes_boss_preference_rules() -> None:
    content = _read("skills/hr-candidate-screening/SKILL.md")

    required_rules = [
        "老板偏好",
        "学校背景好",
        "top 985",
        "211",
        "海外",
        "高潜年轻人",
        "跳槽不能频繁",
        "研发岗位 leader",
        "35岁",
        "带过团队",
        "sig owner",
        "大厂背景",
    ]

    for rule in required_rules:
        assert rule in content


def test_screening_skill_requires_candidate_name_in_recommendation_output() -> None:
    content = _read("skills/hr-candidate-screening/SKILL.md")

    required_rules = [
        "候选人姓名",
        "`name`",
        "每人的 `candidate_id`",
    ]

    for rule in required_rules:
        assert rule in content


def test_analysis_and_report_skills_split_active_and_rejected_candidate_pools() -> None:
    analysis = _read("skills/hr-talent-analysis/SKILL.md")
    report = _read("skills/hr-recruitment-report/SKILL.md")

    for content in [analysis, report]:
        assert "active" in content
        assert "old_rejected" in content
        assert "recent_rejected" in content
        assert "hired" in content


def test_qa_skill_keeps_factual_scope_without_default_recommendation_pool() -> None:
    content = _read("skills/hr-talent-database-qa/SKILL.md")

    assert "事实问答不默认套推荐池策略" in content
    assert "不要基于问答直接生成“推荐/不推荐”结论" in content
