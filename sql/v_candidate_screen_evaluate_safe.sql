CREATE OR REPLACE VIEW v_candidate_screen_evaluate_safe AS
SELECT
    s.id AS screen_evaluate_id,
    s.candidate_id AS candidate_id,
    c.name AS candidate_name,
    c.position_id AS position_id,
    p.name AS position_name,
    c.status AS candidate_status,
    s.screener_id AS screener_id,
    s.feedback AS feedback,
    s.result AS screen_result,
    s.create_time AS create_time,
    s.update_time AS update_time
FROM hr_screen_evaluate s
LEFT JOIN hr_candidate c ON c.id = s.candidate_id
LEFT JOIN hr_position p ON p.id = c.position_id;
