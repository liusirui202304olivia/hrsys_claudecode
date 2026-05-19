CREATE OR REPLACE VIEW v_candidate_interview_evaluate_safe AS
SELECT
    e.id AS evaluation_id,
    e.interview_id AS interview_id,
    i.candidate_id AS candidate_id,
    c.name AS candidate_name,
    c.position_id AS position_id,
    p.name AS position_name,
    c.status AS candidate_status,
    e.interviewer_id AS interviewer_id,
    e.is_primary AS is_primary,
    e.evaluate_data AS evaluate_data,
    e.feedback AS feedback,
    e.result AS evaluation_result,
    e.question_data AS question_data,
    e.create_time AS create_time,
    e.update_time AS update_time
FROM hr_interview_evaluate e
LEFT JOIN hr_interview i ON i.id = e.interview_id
LEFT JOIN hr_candidate c ON c.id = i.candidate_id
LEFT JOIN hr_position p ON p.id = c.position_id;
