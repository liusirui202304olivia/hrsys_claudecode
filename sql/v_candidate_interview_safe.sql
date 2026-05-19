CREATE OR REPLACE VIEW v_candidate_interview_safe AS
SELECT
    i.id AS interview_id,
    i.candidate_id AS candidate_id,
    c.name AS candidate_name,
    c.position_id AS position_id,
    p.name AS position_name,
    c.status AS candidate_status,
    i.name AS interview_name,
    i.interview_type AS interview_type,
    i.interview_time AS interview_time,
    i.status AS interview_status,
    i.create_time AS create_time,
    i.update_time AS update_time
FROM hr_interview i
LEFT JOIN hr_candidate c ON c.id = i.candidate_id
LEFT JOIN hr_position p ON p.id = c.position_id;
