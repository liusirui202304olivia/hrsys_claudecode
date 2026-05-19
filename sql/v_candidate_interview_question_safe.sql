CREATE OR REPLACE VIEW v_candidate_interview_question_safe AS
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
    'evaluate_data' AS item_source,
    jt.item_ord AS question_index,
    jt.score AS score,
    jt.title AS question_title,
    jt.content AS question_content,
    jt.answer AS question_answer,
    jt.feedback AS question_feedback,
    JSON_UNQUOTE(JSON_EXTRACT(jt.item_json, '$.dimensions[0]')) AS dimension,
    e.result AS evaluation_result,
    e.create_time AS create_time,
    e.update_time AS update_time
FROM hr_interview_evaluate e
LEFT JOIN hr_interview i ON i.id = e.interview_id
LEFT JOIN hr_candidate c ON c.id = i.candidate_id
LEFT JOIN hr_position p ON p.id = c.position_id
JOIN JSON_TABLE(
    COALESCE(e.evaluate_data, JSON_ARRAY()),
    '$[*]' COLUMNS (
        item_ord FOR ORDINALITY,
        score DECIMAL(10, 2) PATH '$.score' NULL ON EMPTY NULL ON ERROR,
        title VARCHAR(500) PATH '$.title' NULL ON EMPTY NULL ON ERROR,
        content VARCHAR(4000) PATH '$.content' NULL ON EMPTY NULL ON ERROR,
        answer VARCHAR(4000) PATH '$.answer' NULL ON EMPTY NULL ON ERROR,
        feedback VARCHAR(4000) PATH '$.feedback' NULL ON EMPTY NULL ON ERROR,
        item_json JSON PATH '$'
    )
) jt
UNION ALL
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
    'question_data' AS item_source,
    jt.item_ord AS question_index,
    jt.score AS score,
    jt.title AS question_title,
    jt.content AS question_content,
    jt.answer AS question_answer,
    jt.feedback AS question_feedback,
    JSON_UNQUOTE(JSON_EXTRACT(jt.item_json, '$.dimensions[0]')) AS dimension,
    e.result AS evaluation_result,
    e.create_time AS create_time,
    e.update_time AS update_time
FROM hr_interview_evaluate e
LEFT JOIN hr_interview i ON i.id = e.interview_id
LEFT JOIN hr_candidate c ON c.id = i.candidate_id
LEFT JOIN hr_position p ON p.id = c.position_id
JOIN JSON_TABLE(
    COALESCE(e.question_data, JSON_ARRAY()),
    '$[*]' COLUMNS (
        item_ord FOR ORDINALITY,
        score DECIMAL(10, 2) PATH '$.score' NULL ON EMPTY NULL ON ERROR,
        title VARCHAR(500) PATH '$.title' NULL ON EMPTY NULL ON ERROR,
        content VARCHAR(4000) PATH '$.content' NULL ON EMPTY NULL ON ERROR,
        answer VARCHAR(4000) PATH '$.answer' NULL ON EMPTY NULL ON ERROR,
        feedback VARCHAR(4000) PATH '$.feedback' NULL ON EMPTY NULL ON ERROR,
        item_json JSON PATH '$'
    )
) jt;
