CREATE OR REPLACE VIEW v_candidate_agent_privileged AS
SELECT
    c.id AS candidate_id,
    c.position_id,
    c.source_id,
    c.status,
    c.reject_stage,
    c.hr_id,
    c.name,
    c.gender,
    c.degree_first,
    c.degree,
    c.degree_start,
    c.degree_end,
    c.college,
    c.major,
    c.work_years,
    c.experiences,
    c.latest_interview_id,
    c.proposed_join_date,
    c.proposed_department_id,
    c.is_focused,
    c.match_point,
    c.create_time,
    c.update_time,
    c.manual_import,
    c.project_experiences,
    c.skills,
    c.mobile,
    c.email,
    p.name AS position_name,
    p.category AS position_category,
    p.jd AS position_jd,
    p.is_active AS position_is_active,
    s.name AS source_name,
    s.full_name AS source_full_name,
    f.follower_ids,
    i.interviewer_ids
FROM hr_candidate c
LEFT JOIN hr_position p ON p.id = c.position_id
LEFT JOIN hr_source s ON s.id = c.source_id
LEFT JOIN (
    SELECT
        candidate_id,
        GROUP_CONCAT(DISTINCT follower_id ORDER BY follower_id) AS follower_ids
    FROM hr_candidate_follower
    WHERE is_current = 1
    GROUP BY candidate_id
) f ON f.candidate_id = c.id
LEFT JOIN (
    SELECT iv.candidate_id, GROUP_CONCAT(DISTINCT ev.interviewer_id ORDER BY ev.interviewer_id) AS interviewer_ids
    FROM hr_interview iv
    INNER JOIN hr_interview_evaluate ev ON ev.interview_id = iv.id
    WHERE ev.interviewer_id IS NOT NULL
    GROUP BY iv.candidate_id
) i ON i.candidate_id = c.id;
