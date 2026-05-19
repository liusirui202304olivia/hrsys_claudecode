"""SQL 安全视图定义测试。

该文件直接检查 `sql/` 下的安全视图脚本，确保 MySQL 真实库部署时保持一候选人一行的数据契约。
测试重点保护 follower 聚合、interviewer 聚合和联系方式隔离，避免 repository 在 `COUNT(*)`、分页和分布统计时被多行 join 放大。
这些测试不连接真实数据库，只验证项目维护的 SQL 视图定义是否符合安全数据服务的结构要求。
"""

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


INTERVIEW_OPERATIONAL_FIELDS = {
    "showmebug_id",
    "exam_id",
    "exam_name",
    "candidate_link",
    "interviewer_link",
    "calendar_event_id",
}


def read_sql(name):
    return (PROJECT_ROOT / "sql" / name).read_text(encoding="utf-8")


def test_safe_view_aggregates_followers_and_does_not_join_follower_rows_directly():
    sql = read_sql("v_candidate_agent_safe.sql")

    assert "f.follower_ids" in sql
    assert "GROUP_CONCAT(DISTINCT follower_id" in sql
    assert "FROM hr_candidate_follower" in sql
    assert "GROUP BY candidate_id" in sql
    assert "LEFT JOIN hr_candidate_follower f" not in sql
    assert re.search(r"\bf\.follower_id\b", sql) is None


def test_privileged_view_aggregates_followers_and_keeps_same_candidate_grain():
    sql = read_sql("v_candidate_agent_privileged.sql")

    assert "f.follower_ids" in sql
    assert "GROUP_CONCAT(DISTINCT follower_id" in sql
    assert "GROUP BY candidate_id" in sql
    assert "LEFT JOIN hr_candidate_follower f" not in sql
    assert re.search(r"\bf\.follower_id\b", sql) is None


def test_privileged_view_only_adds_candidate_contact_fields_over_safe_view():
    safe_sql = read_sql("v_candidate_agent_safe.sql")
    privileged_sql = read_sql("v_candidate_agent_privileged.sql")

    assert "c.mobile" not in safe_sql
    assert "c.email" not in safe_sql
    assert "c.mobile" in privileged_sql
    assert "c.email" in privileged_sql
    assert _without_privileged_contact_fields(privileged_sql) == _normalise_view_name(safe_sql)


def test_interview_safe_views_are_defined_without_operational_fields():
    for filename in [
        "v_candidate_interview_safe.sql",
        "v_candidate_interview_evaluate_safe.sql",
        "v_candidate_interview_question_safe.sql",
        "v_candidate_screen_evaluate_safe.sql",
    ]:
        sql = read_sql(filename).lower()
        for field_name in INTERVIEW_OPERATIONAL_FIELDS:
            assert field_name not in sql


def test_interview_safe_view_exposes_agent_safe_aliases():
    sql = read_sql("v_candidate_interview_safe.sql")

    for field_name in [
        "interview_id",
        "candidate_id",
        "candidate_name",
        "position_id",
        "position_name",
        "candidate_status",
        "interview_name",
        "interview_type",
        "interview_time",
        "interview_status",
        "create_time",
        "update_time",
    ]:
        assert re.search(r"\bAS\s+" + re.escape(field_name) + r"\b", sql, flags=re.IGNORECASE)


def test_interview_evaluate_safe_view_exposes_feedback_and_json_payloads():
    sql = read_sql("v_candidate_interview_evaluate_safe.sql")

    for field_name in [
        "evaluation_id",
        "interview_id",
        "candidate_id",
        "candidate_name",
        "position_id",
        "position_name",
        "candidate_status",
        "interviewer_id",
        "is_primary",
        "evaluate_data",
        "feedback",
        "evaluation_result",
        "question_data",
        "create_time",
        "update_time",
    ]:
        assert re.search(r"\bAS\s+" + re.escape(field_name) + r"\b", sql, flags=re.IGNORECASE)


def test_interview_question_safe_view_expands_question_and_score_fields():
    sql = read_sql("v_candidate_interview_question_safe.sql")

    assert "json_table" in sql.lower()
    for field_name in [
        "evaluation_id",
        "interview_id",
        "candidate_id",
        "candidate_name",
        "position_id",
        "position_name",
        "candidate_status",
        "interviewer_id",
        "is_primary",
        "item_source",
        "question_index",
        "score",
        "question_title",
        "question_content",
        "question_answer",
        "question_feedback",
        "dimension",
        "evaluation_result",
        "create_time",
        "update_time",
    ]:
        assert re.search(r"\bAS\s+" + re.escape(field_name) + r"\b", sql, flags=re.IGNORECASE)


def test_screen_evaluate_safe_view_exposes_agent_safe_aliases():
    sql = read_sql("v_candidate_screen_evaluate_safe.sql")

    for field_name in [
        "screen_evaluate_id",
        "candidate_id",
        "candidate_name",
        "position_id",
        "position_name",
        "candidate_status",
        "screener_id",
        "feedback",
        "screen_result",
        "create_time",
        "update_time",
    ]:
        assert re.search(r"\bAS\s+" + re.escape(field_name) + r"\b", sql, flags=re.IGNORECASE)


def _without_privileged_contact_fields(sql):
    kept_lines = []
    for line in sql.splitlines():
        if line.strip() in {"c.mobile,", "c.email,"}:
            continue
        kept_lines.append(line)
    return _normalise_view_name("\n".join(kept_lines))


def _normalise_view_name(sql):
    return sql.replace("v_candidate_agent_privileged", "v_candidate_agent_safe").lstrip("\ufeff").strip()
