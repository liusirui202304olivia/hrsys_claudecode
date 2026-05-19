"""SQL dump 与 MySQL repository 测试。

该文件用小型 SQL dump fixture 验证表结构解析、候选人/岗位/来源联表、受控 filter 和岗位分布计算。
同时检查未知 filter 会被拒绝，并确认 MySQL repository 走安全视图而不是直接 `SELECT c.*` 原表。
这些测试保证数据访问层可用于离线验证，并维持 P0 不暴露自由 SQL 的约束。
"""

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import inspect
import pytest

from hr_mcp.repositories.dump_repository import DumpTalentRepository
from hr_mcp.repositories.mysql_repository import MySQLTalentRepository


SAMPLE_DUMP = r'''
CREATE TABLE `hr_candidate` (
  `id` int NOT NULL AUTO_INCREMENT,
  `source_id` int NOT NULL COMMENT '简历来源',
  `position_id` int NOT NULL COMMENT '岗位ID',
  `status` varchar(50) NOT NULL COMMENT '状态',
  `hr_id` int NOT NULL COMMENT '责任HR',
  `name` varchar(100) DEFAULT NULL COMMENT '姓名',
  `gender` varchar(20) DEFAULT NULL COMMENT '性别',
  `degree_first` varchar(20) DEFAULT NULL COMMENT '第一学历',
  `degree` varchar(20) DEFAULT NULL COMMENT '最高学历',
  `college` varchar(500) DEFAULT NULL COMMENT '最高学历学校',
  `major` varchar(500) DEFAULT NULL COMMENT '最高学历专业',
  `work_years` int DEFAULT NULL COMMENT '工作年限',
  `experiences` json DEFAULT NULL COMMENT '履历',
  `proposed_join_date` date DEFAULT NULL COMMENT '拟入职时间',
  `project_experiences` json DEFAULT (_utf8mb4'[]') COMMENT '项目经历',
  `skills` json DEFAULT (_utf8mb4'[]') COMMENT '技术栈',
  `is_focused` tinyint(1) DEFAULT '0' COMMENT '是否关注',
  `match_point` int DEFAULT NULL COMMENT '匹配点',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
  `manual_import` tinyint(1) DEFAULT '1' COMMENT '手工导入',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='候选人';
INSERT INTO `hr_candidate` VALUES
(1,10,20,'SCREEN_PROCESS',2,'张三','MALE','BACHELOR','BACHELOR','四川大学','计算机',5,'[{"company":"华为","position":"C++工程师"}]','2026-06-01','[{"project":"CPU模型","content":"负责gem5性能建模"}]','["C++","gem5"]',1,90,'2026-05-01 10:00:00','2026-05-02 10:00:00',1),
(2,10,21,'REJECTED',3,'李四','FEMALE','BACHELOR','BACHELOR','电子科大','软件工程',1,'[]',NULL,'[]','["Java"]',0,40,'2026-04-01 10:00:00','2026-04-02 10:00:00',0);

CREATE TABLE `hr_position` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL COMMENT '岗位名称',
  `category` varchar(20) NOT NULL COMMENT '岗位类别',
  `jd` text NOT NULL COMMENT '职位描述',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='岗位';
INSERT INTO `hr_position` VALUES
(20,'芯片建模工程师','DEV','负责CPU性能建模',1),
(21,'应用软件开发工程师','DEV','负责C++系统软件',1);

CREATE TABLE `hr_source` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `name` varchar(255) NOT NULL COMMENT '名称',
  `full_name` varchar(255) NOT NULL COMMENT '全称',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='简历来源';
INSERT INTO `hr_source` VALUES (10,'历史导入','其他/历史导入');

CREATE TABLE `hr_interview` (
  `id` int NOT NULL AUTO_INCREMENT,
  `candidate_id` int NOT NULL COMMENT '候选人ID',
  `name` varchar(100) DEFAULT NULL COMMENT '面试名称',
  `interview_type` varchar(50) DEFAULT NULL COMMENT '面试类型',
  `interview_time` datetime DEFAULT NULL COMMENT '面试时间',
  `showmebug_id` varchar(64) DEFAULT NULL COMMENT '平台内部ID',
  `exam_id` varchar(64) DEFAULT NULL COMMENT '考试ID',
  `exam_name` varchar(255) DEFAULT NULL COMMENT '考试名称',
  `candidate_link` varchar(500) DEFAULT NULL COMMENT '候选人链接',
  `interviewer_link` varchar(500) DEFAULT NULL COMMENT '面试官链接',
  `calendar_event_id` varchar(128) DEFAULT NULL COMMENT '日程ID',
  `status` varchar(50) DEFAULT NULL COMMENT '状态',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='面试';
INSERT INTO `hr_interview` VALUES
(100,1,'技术一面','TECH','2026-05-03 10:00:00','sb-1','exam-1','内部考试','https://candidate','https://interviewer','cal-1','PASSED','2026-05-01 10:00:00','2026-05-03 12:00:00'),
(101,1,'技术二面','TECH','2026-05-04 10:00:00','sb-2','exam-2','内部考试','https://candidate','https://interviewer','cal-2','PASSED','2026-05-02 10:00:00','2026-05-04 12:00:00'),
(102,2,'HR面','HR','2026-05-05 10:00:00','sb-3','exam-3','内部考试','https://candidate','https://interviewer','cal-3','REJECTED','2026-05-03 10:00:00','2026-05-05 12:00:00');

CREATE TABLE `hr_interview_evaluate` (
  `id` int NOT NULL AUTO_INCREMENT,
  `interview_id` int NOT NULL COMMENT '面试ID',
  `interviewer_id` int NOT NULL COMMENT '面试官ID',
  `is_primary` tinyint(1) DEFAULT '0' COMMENT '是否主面',
  `evaluate_data` json DEFAULT NULL COMMENT '评价 JSON',
  `feedback` text COMMENT '评价反馈',
  `result` varchar(50) DEFAULT NULL COMMENT '评价结果',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `question_data` json DEFAULT NULL COMMENT '问答 JSON',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='面试评价';
INSERT INTO `hr_interview_evaluate` VALUES
(1000,100,42,1,'[{"score":88,"feedback":"C++基础扎实","dimensions":["基础"]}]','整体工程经验扎实','PASS','2026-05-03 11:00:00','2026-05-03 12:00:00','[{"title":"算法题","content":"解释锁竞争","answer":"从临界区和调度分析","feedback":"回答完整","dimensions":["系统"]}]'),
(1001,101,43,0,'[{"score":92,"feedback":"建模经验匹配","dimensions":["建模"]}]','芯片建模匹配度高','PASS','2026-05-04 11:00:00','2026-05-04 12:00:00','[{"title":"建模题","content":"如何做性能瓶颈分析","answer":"使用profile和trace","feedback":"思路清楚","dimensions":["性能"]}]'),
(1002,102,99,1,'[{"score":50,"feedback":"经验不足","dimensions":["综合"]}]','不建议推进','REJECTED','2026-05-05 11:00:00','2026-05-05 12:00:00','[{"title":"沟通题","content":"项目冲突处理","answer":"缺少细节","feedback":"需要补充","dimensions":["沟通"]}]');

CREATE TABLE `hr_screen_evaluate` (
  `id` int NOT NULL AUTO_INCREMENT,
  `candidate_id` int NOT NULL COMMENT '候选人ID',
  `screener_id` int NOT NULL COMMENT '初筛人ID',
  `feedback` text COMMENT '初筛反馈',
  `result` varchar(50) DEFAULT NULL COMMENT '初筛结果',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='初筛评价';
INSERT INTO `hr_screen_evaluate` VALUES
(5000,1,8,'简历与芯片建模岗位匹配','PASS','2026-05-01 09:00:00','2026-05-01 09:30:00'),
(5001,2,8,'工作年限偏短','REJECTED','2026-04-01 09:00:00','2026-04-01 09:30:00');
'''


POOL_FILTER_DUMP = r'''
CREATE TABLE `hr_candidate` (
  `id` int NOT NULL AUTO_INCREMENT,
  `source_id` int NOT NULL COMMENT '简历来源',
  `position_id` int NOT NULL COMMENT '岗位ID',
  `status` varchar(50) NOT NULL COMMENT '状态',
  `hr_id` int NOT NULL COMMENT '责任HR',
  `name` varchar(100) DEFAULT NULL COMMENT '姓名',
  `work_years` int DEFAULT NULL COMMENT '工作年限',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间, 触发器跟随status',
  `experiences` json DEFAULT NULL COMMENT '履历',
  `project_experiences` json DEFAULT (_utf8mb4'[]') COMMENT '项目经历',
  `skills` json DEFAULT (_utf8mb4'[]') COMMENT '技术栈',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='候选人';
INSERT INTO `hr_candidate` VALUES
(1,10,20,'SCREEN_PROCESS',2,'流程中候选人',5,'2026-05-01 10:00:00','[]','[]','["C++"]'),
(2,10,20,'REJECTED',2,'近期拒绝候选人',6,'2099-04-01 10:00:00','[]','[]','["C++"]'),
(3,10,20,'REJECTED',2,'历史拒绝候选人',7,'2000-01-01 10:00:00','[]','[]','["C++"]'),
(4,10,20,'HIRED',2,'已入职候选人',8,'2026-03-01 10:00:00','[]','[]','["C++"]');

CREATE TABLE `hr_position` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL COMMENT '岗位名称',
  `category` varchar(20) NOT NULL COMMENT '岗位类别',
  `jd` text NOT NULL COMMENT '职位描述',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='岗位';
INSERT INTO `hr_position` VALUES
(20,'CPU性能建模工程师','DEV','负责CPU性能建模',1);

CREATE TABLE `hr_source` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `name` varchar(255) NOT NULL COMMENT '名称',
  `full_name` varchar(255) NOT NULL COMMENT '全称',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='简历来源';
INSERT INTO `hr_source` VALUES (10,'历史导入','其他/历史导入');
'''


def write_dump(tmp_path: Path) -> Path:
    dump_path = tmp_path / "sample.sql"
    dump_path.write_text(SAMPLE_DUMP, encoding="utf-8")
    return dump_path


def write_pool_filter_dump(tmp_path: Path) -> Path:
    dump_path = tmp_path / "pool_filter.sql"
    dump_path.write_text(POOL_FILTER_DUMP, encoding="utf-8")
    return dump_path


def test_dump_repository_parses_schema_and_joined_rows(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    page = repo.search_candidates({"position_query": "芯片建模"}, page_size=10)
    candidates = page["items"]

    assert len(candidates) == 1
    assert page["total_count"] == 1
    assert page["has_more"] is False
    assert candidates[0]["id"] == 1
    assert candidates[0]["name"] == "张三"
    assert candidates[0]["position_name"] == "芯片建模工程师"
    assert candidates[0]["source_name"] == "历史导入"
    assert candidates[0]["interviewer_ids"] == [42, 43]


def test_dump_repository_executes_interview_safe_view_queries(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    rows = repo.execute_safe_sql(
        "SELECT interview_id, candidate_id, candidate_name, interview_name, interview_status "
        "FROM v_candidate_interview_safe WHERE candidate_id = 1 ORDER BY interview_id LIMIT 10"
    )

    assert rows == [
        {
            "interview_id": "100",
            "candidate_id": "1",
            "candidate_name": "张三",
            "interview_name": "技术一面",
            "interview_status": "PASSED",
        },
        {
            "interview_id": "101",
            "candidate_id": "1",
            "candidate_name": "张三",
            "interview_name": "技术二面",
            "interview_status": "PASSED",
        },
    ]


def test_dump_repository_executes_interview_evaluate_safe_view_queries(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    rows = repo.execute_safe_sql(
        "SELECT candidate_id, candidate_name, feedback, evaluation_result, question_data "
        "FROM v_candidate_interview_evaluate_safe WHERE candidate_id = 1 ORDER BY evaluation_id LIMIT 10"
    )

    assert len(rows) == 2
    assert rows[0]["feedback"] == "整体工程经验扎实"
    assert rows[0]["evaluation_result"] == "PASS"
    assert "算法题" in rows[0]["question_data"]


def test_dump_repository_executes_interview_question_aggregation(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    rows = repo.execute_safe_sql(
        "SELECT interviewer_id, AVG(score) AS avg_score, COUNT(*) AS count "
        "FROM v_candidate_interview_question_safe "
        "WHERE item_source = 'evaluate_data' GROUP BY interviewer_id ORDER BY interviewer_id LIMIT 10"
    )

    assert rows == [
        {"interviewer_id": "42", "avg_score": 88.0, "count": 1},
        {"interviewer_id": "43", "avg_score": 92.0, "count": 1},
        {"interviewer_id": "99", "avg_score": 50.0, "count": 1},
    ]


def test_dump_repository_executes_screen_evaluate_safe_view_queries(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    rows = repo.execute_safe_sql(
        "SELECT screen_evaluate_id, candidate_id, candidate_name, feedback, screen_result "
        "FROM v_candidate_screen_evaluate_safe WHERE candidate_id = 1 LIMIT 10"
    )

    assert rows == [
        {
            "screen_evaluate_id": "5000",
            "candidate_id": "1",
            "candidate_name": "张三",
            "feedback": "简历与芯片建模岗位匹配",
            "screen_result": "PASS",
        }
    ]


def test_dump_repository_filters_status_keyword_and_work_years(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    page = repo.search_candidates(
        {
            "status": ["SCREEN_PROCESS"],
            "skills_any": ["gem5"],
            "min_work_years": 3,
        },
        page_size=10,
    )
    candidates = page["items"]

    assert [row["name"] for row in candidates] == ["张三"]


def test_dump_repository_filters_high_frequency_business_dimensions(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    by_name = repo.search_candidates({"name_query": "张"}, page_size=10)
    by_join_date = repo.search_candidates({"proposed_join_date_from": "2026-06-01", "proposed_join_date_to": "2026-06-30"}, page_size=10)
    by_created = repo.search_candidates({"create_time_from": "2026-05-01", "create_time_to": "2026-05-31"}, page_size=10)
    by_school = repo.search_candidates({"college_query": "四川", "major_query": "计算机"}, page_size=10)
    by_flags = repo.search_candidates({"gender": "MALE", "max_work_years": 6, "is_focused": True, "manual_import": True, "match_point_min": 80}, page_size=10)
    upcoming = repo.search_candidates({"candidate_pool": "joining", "proposed_join_date_from": "2026-06-01", "proposed_join_date_to": "2026-06-30"}, page_size=10)

    assert [row["name"] for row in by_name["items"]] == ["张三"]
    assert [row["name"] for row in by_join_date["items"]] == ["张三"]
    assert [row["name"] for row in by_created["items"]] == ["张三"]
    assert [row["name"] for row in by_school["items"]] == ["张三"]
    assert [row["name"] for row in by_flags["items"]] == ["张三"]
    assert [row["name"] for row in upcoming["items"]] == ["张三"]


def test_dump_repository_position_query_matches_position_name_or_jd(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    page = repo.search_candidates({"position_query": "系统软件"}, page_size=10)

    assert [row["name"] for row in page["items"]] == ["李四"]
    assert page["items"][0]["position_name"] == "应用软件开发工程师"


def test_dump_repository_computes_position_distribution(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    distribution = repo.position_distribution({})

    assert distribution == [
        {"position_name": "应用软件开发工程师", "count": 1},
        {"position_name": "芯片建模工程师", "count": 1},
    ]


def test_dump_repository_computes_extended_distributions(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    assert repo.distribution("gender", {}) == [
        {"gender": "FEMALE", "count": 1},
        {"gender": "MALE", "count": 1},
    ]
    assert repo.distribution("proposed_join_month", {}) == [
        {"proposed_join_month": "2026-06", "count": 1},
        {"proposed_join_month": "UNKNOWN", "count": 1},
    ]
    assert repo.distribution("work_years_band", {}) == [
        {"work_years_band": "0-2", "count": 1},
        {"work_years_band": "3-5", "count": 1},
    ]


def test_dump_repository_rejects_unknown_filters(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    with pytest.raises(ValueError):
        repo.search_candidates({"free_sql": "status = 'x'"}, page_size=10)


def test_dump_repository_search_paginates_without_changing_total_count(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    first_page = repo.search_candidates({}, page_size=1)
    second_page = repo.search_candidates({}, page_size=1, cursor=first_page["next_cursor"])

    assert len(first_page["items"]) == 1
    assert first_page["total_count"] == 2
    assert first_page["has_more"] is True
    assert first_page["next_cursor"]
    assert len(second_page["items"]) == 1
    assert second_page["total_count"] == 2
    assert second_page["has_more"] is False


def test_dump_repository_filters_candidate_pools_and_status_update_dates(tmp_path: Path):
    repo = DumpTalentRepository(write_pool_filter_dump(tmp_path))

    active = repo.search_candidates({"candidate_pool": "active"}, page_size=10)
    old_rejected = repo.search_candidates({"candidate_pool": "old_rejected", "rejected_before_days": 180}, page_size=10)
    recent_rejected = repo.search_candidates({"candidate_pool": "recent_rejected", "rejected_before_days": 180}, page_size=10)
    hired = repo.search_candidates({"candidate_pool": "hired"}, page_size=10)
    joining = repo.search_candidates({"candidate_pool": "joining"}, page_size=10)
    stale = repo.search_candidates({"status_updated_before": "2025-12-01"}, page_size=10)

    assert [row["name"] for row in active["items"]] == ["流程中候选人"]
    assert [row["name"] for row in old_rejected["items"]] == ["历史拒绝候选人"]
    assert [row["name"] for row in recent_rejected["items"]] == ["近期拒绝候选人"]
    assert [row["name"] for row in hired["items"]] == ["已入职候选人"]
    assert [row["name"] for row in joining["items"]] == []
    assert [row["name"] for row in stale["items"]] == ["历史拒绝候选人"]


def test_dump_repository_rejects_conflicting_pool_and_status_filter(tmp_path: Path):
    repo = DumpTalentRepository(write_pool_filter_dump(tmp_path))

    with pytest.raises(ValueError):
        repo.search_candidates({"candidate_pool": "active", "status": ["SCREEN_PROCESS"]}, page_size=10)


def test_mysql_repository_uses_safe_view_by_default_and_privileged_only_when_requested():
    class RecordingRepo(MySQLTalentRepository):
        def __init__(self):
            super().__init__({"host": "localhost", "user": "u", "password": "p", "database": "d"})
            self.last_sql = ""

        def _fetch_all(self, sql, params):
            self.last_sql = sql
            return []

    repo = RecordingRepo()

    repo.search_candidates({}, page_size=10)
    assert "v_candidate_agent_safe" in repo.last_sql
    assert "v_candidate_agent_privileged" not in repo.last_sql

    repo.search_candidates({}, page_size=10, include_privileged=True)
    assert "v_candidate_agent_privileged" in repo.last_sql

    source = inspect.getsource(MySQLTalentRepository)

    assert "SELECT c.*" not in source


def test_mysql_repository_search_uses_keyset_pagination_and_page_size_plus_one():
    class RecordingRepo(MySQLTalentRepository):
        def __init__(self):
            super().__init__({"host": "localhost", "user": "u", "password": "p", "database": "d"})
            self.last_sql = ""
            self.last_params = []
            self.sqls = []
            self.params_list = []

        def _fetch_all(self, sql, params):
            self.last_sql = sql
            self.last_params = params
            self.sqls.append(sql)
            self.params_list.append(params)
            return [
                {"candidate_id": 2, "update_time": "2026-01-02 00:00:00", "name": "A"},
                {"candidate_id": 1, "update_time": "2026-01-01 00:00:00", "name": "B"},
            ]

    repo = RecordingRepo()

    page = repo.search_candidates({}, page_size=1)

    assert page["items"] == [{"candidate_id": 2, "update_time": "2026-01-02 00:00:00", "name": "A"}]
    assert page["has_more"] is True
    assert page["next_cursor"]
    assert "ORDER BY COALESCE(v.update_time" in repo.sqls[0]
    assert "v.candidate_id DESC" in repo.sqls[0]
    assert repo.params_list[0][-1] == 2


def test_mysql_repository_count_and_distributions_use_sql_aggregates():
    class RecordingRepo(MySQLTalentRepository):
        def __init__(self):
            super().__init__({"host": "localhost", "user": "u", "password": "p", "database": "d"})
            self.sqls = []

        def _fetch_all(self, sql, params):
            self.sqls.append(sql)
            if "COUNT(*) AS total_count" in sql:
                return [{"total_count": 123}]
            return [{"position_name": "芯片建模工程师", "count": 12}]

    repo = RecordingRepo()

    assert repo.count_candidates({}) == 123
    assert repo.position_distribution({}) == [{"position_name": "芯片建模工程师", "count": 12}]
    combined_sql = "\n".join(repo.sqls)

    assert "COUNT(*) AS total_count" in combined_sql
    assert "GROUP BY v.position_name" in combined_sql
    assert "search_candidates(filters" not in inspect.getsource(MySQLTalentRepository)


@pytest.mark.parametrize(
    "identity_scope",
    [
        {"role": "RECRUITER", "user_id": 42},
        {"role": "DEPARTMENT_MANAGER", "department_id": 7},
        {"role": "INTERVIEWER", "user_id": 42},
    ],
)
def test_mysql_repository_business_roles_do_not_add_row_scope_filters(identity_scope):
    class RecordingRepo(MySQLTalentRepository):
        def __init__(self):
            super().__init__({"host": "localhost", "user": "u", "password": "p", "database": "d"})
            self.sqls = []
            self.params_list = []

        def _fetch_all(self, sql, params):
            self.sqls.append(sql)
            self.params_list.append(params)
            if "COUNT(*) AS total_count" in sql:
                return [{"total_count": 1}]
            return [{"candidate_id": 1, "update_time": "2026-01-01 00:00:00"}]

    repo = RecordingRepo()

    repo.search_candidates({}, page_size=10, identity_scope=identity_scope)
    combined_sql = "\n".join(repo.sqls)

    assert "FIND_IN_SET(%s, COALESCE(v.follower_ids, ''))" not in combined_sql
    assert "FIND_IN_SET(%s, COALESCE(v.interviewer_ids, ''))" not in combined_sql
    assert "v.proposed_department_id = %s" not in combined_sql
    assert "v.hr_id = %s" not in combined_sql
    assert re.search(r"\bv\.follower_id\b", combined_sql) is None
    assert repo.params_list[0] == [11]


def test_mysql_repository_position_query_matches_position_name_or_jd():
    class RecordingRepo(MySQLTalentRepository):
        def __init__(self):
            super().__init__({"host": "localhost", "user": "u", "password": "p", "database": "d"})
            self.sqls = []
            self.params_list = []

        def _fetch_all(self, sql, params):
            self.sqls.append(sql)
            self.params_list.append(params)
            if "COUNT(*) AS total_count" in sql:
                return [{"total_count": 1}]
            return [{"candidate_id": 1, "update_time": "2026-01-01 00:00:00"}]

    repo = RecordingRepo()

    repo.search_candidates({"position_query": "系统软件"}, page_size=10)
    search_sql = repo.sqls[0]

    assert "(v.position_name LIKE %s OR v.position_jd LIKE %s)" in search_sql
    assert repo.params_list[0][:2] == ["%系统软件%", "%系统软件%"]


def test_mysql_repository_filters_high_frequency_business_dimensions():
    class RecordingRepo(MySQLTalentRepository):
        def __init__(self):
            super().__init__({"host": "localhost", "user": "u", "password": "p", "database": "d"})
            self.sqls = []
            self.params_list = []

        def _fetch_all(self, sql, params):
            self.sqls.append(sql)
            self.params_list.append(params)
            if "COUNT(*) AS total_count" in sql:
                return [{"total_count": 1}]
            return [{"candidate_id": 1, "update_time": "2026-01-01 00:00:00"}]

    repo = RecordingRepo()

    repo.search_candidates(
        {
            "name_query": "张",
            "proposed_join_date_from": "2026-05-01",
            "proposed_join_date_to": "2026-05-31",
            "create_time_from": "2026-04-01",
            "create_time_to": "2026-04-30",
            "update_time_from": "2026-03-01",
            "update_time_to": "2026-03-31",
            "source_query": "内推",
            "degree": "BACHELOR",
            "college_query": "四川",
            "major_query": "计算机",
            "gender": "MALE",
            "max_work_years": 8,
            "is_focused": True,
            "manual_import": False,
            "match_point_min": 60,
            "proposed_department_id": 7,
            "hr_id": 2,
        },
        page_size=10,
    )
    search_sql = repo.sqls[0]
    params = repo.params_list[0]

    assert "v.name LIKE %s" in search_sql
    assert "v.proposed_join_date >= %s" in search_sql
    assert "v.proposed_join_date <= %s" in search_sql
    assert "v.create_time >= %s" in search_sql
    assert "v.update_time <= %s" in search_sql
    assert "(v.source_name LIKE %s OR v.source_full_name LIKE %s)" in search_sql
    assert "v.college LIKE %s" in search_sql
    assert "v.major LIKE %s" in search_sql
    assert "v.work_years <= %s" in search_sql
    assert "v.is_focused = %s" in search_sql
    assert "v.manual_import = %s" in search_sql
    assert "v.match_point >= %s" in search_sql
    assert "%张%" in params


def test_mysql_repository_joining_pool_excludes_rejected_and_hired():
    class RecordingRepo(MySQLTalentRepository):
        def __init__(self):
            super().__init__({"host": "localhost", "user": "u", "password": "p", "database": "d"})
            self.sqls = []

        def _fetch_all(self, sql, params):
            self.sqls.append(sql)
            if "COUNT(*) AS total_count" in sql:
                return [{"total_count": 1}]
            return [{"candidate_id": 1, "update_time": "2026-01-01 00:00:00"}]

    repo = RecordingRepo()

    repo.search_candidates({"candidate_pool": "joining"}, page_size=10)

    assert "v.proposed_join_date IS NOT NULL" in repo.sqls[0]
    assert "v.status NOT IN ('REJECTED', 'HIRED')" in repo.sqls[0]


def test_mysql_repository_skill_and_experience_keywords_use_any_or_semantics():
    class RecordingRepo(MySQLTalentRepository):
        def __init__(self):
            super().__init__({"host": "localhost", "user": "u", "password": "p", "database": "d"})
            self.sqls = []
            self.params_list = []

        def _fetch_all(self, sql, params):
            self.sqls.append(sql)
            self.params_list.append(params)
            if "COUNT(*) AS total_count" in sql:
                return [{"total_count": 1}]
            return [{"candidate_id": 1, "update_time": "2026-01-01 00:00:00"}]

    repo = RecordingRepo()

    repo.search_candidates(
        {"skills_any": ["C++", "Python"], "experience_keywords_any": ["gem5"]},
        page_size=10,
    )
    search_sql = repo.sqls[0]

    assert search_sql.count("v.skills LIKE %s") == 3
    assert " OR (v.skills LIKE %s OR v.experiences LIKE %s OR v.project_experiences LIKE %s)" in search_sql
    assert "AND (v.skills LIKE %s OR v.experiences LIKE %s OR v.project_experiences LIKE %s)\n            AND" not in search_sql


def test_mysql_repository_candidate_pool_filters_are_controlled_sql_conditions():
    class RecordingRepo(MySQLTalentRepository):
        def __init__(self):
            super().__init__({"host": "localhost", "user": "u", "password": "p", "database": "d"})
            self.sqls = []
            self.params_list = []

        def _fetch_all(self, sql, params):
            self.sqls.append(sql)
            self.params_list.append(params)
            if "COUNT(*) AS total_count" in sql:
                return [{"total_count": 1}]
            return [{"candidate_id": 1, "update_time": "2025-01-01 00:00:00"}]

    repo = RecordingRepo()

    repo.search_candidates({"candidate_pool": "active"}, page_size=10)
    repo.search_candidates({"candidate_pool": "old_rejected", "rejected_before_days": 180}, page_size=10)
    repo.search_candidates({"candidate_pool": "recent_rejected", "rejected_before_days": 180}, page_size=10)
    repo.search_candidates({"candidate_pool": "hired", "status_updated_after": "2026-01-01"}, page_size=10)
    combined_sql = "\n".join(repo.sqls)
    combined_params = [item for params in repo.params_list for item in params]

    assert "v.status NOT IN ('REJECTED', 'HIRED')" in combined_sql
    assert "v.status = %s AND v.update_time <= %s" in combined_sql
    assert "v.status = %s AND v.update_time > %s" in combined_sql
    assert "v.status = %s" in combined_sql
    assert "v.update_time >= %s" in combined_sql
    assert "REJECTED" in combined_params
    assert "HIRED" in combined_params


def test_mysql_repository_generic_distribution_uses_whitelisted_expressions():
    class RecordingRepo(MySQLTalentRepository):
        def __init__(self):
            super().__init__({"host": "localhost", "user": "u", "password": "p", "database": "d"})
            self.sqls = []

        def _fetch_all(self, sql, params):
            self.sqls.append(sql)
            return [{"proposed_join_month": "2026-06", "count": 2}]

    repo = RecordingRepo()

    result = repo.distribution("proposed_join_month", {})

    assert result == [{"proposed_join_month": "2026-06", "count": 2}]
    assert "DATE_FORMAT(v.proposed_join_date, '%Y-%m')" in repo.sqls[-1]
    with pytest.raises(ValueError):
        repo.distribution("free_sql", {})


def test_mysql_repository_rejects_pool_status_conflict_and_bad_dates():
    repo = MySQLTalentRepository({"host": "localhost", "user": "u", "password": "p", "database": "d"})

    with pytest.raises(ValueError):
        repo.search_candidates({"candidate_pool": "active", "status": ["SCREEN_PROCESS"]}, page_size=10)
    with pytest.raises(ValueError):
        repo.search_candidates({"candidate_pool": "bad"}, page_size=10)
    with pytest.raises(ValueError):
        repo.search_candidates({"candidate_pool": "old_rejected", "rejected_before_days": True}, page_size=10)
    with pytest.raises(ValueError):
        repo.search_candidates({"status_updated_before": "2026/01/01"}, page_size=10)


def test_mysql_repository_ready_checks_all_safe_views(monkeypatch):
    executed_sql = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            executed_sql.append(sql)

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def close(self):
            pass

    fake_pymysql = SimpleNamespace(
        connect=lambda **kwargs: FakeConnection(),
        cursors=SimpleNamespace(DictCursor=object),
    )
    monkeypatch.setitem(sys.modules, "pymysql", fake_pymysql)

    repo = MySQLTalentRepository({"host": "localhost", "user": "u", "password": "p", "database": "d"})

    assert repo.ready() is True
    combined_sql = "\n".join(executed_sql)
    assert "SELECT candidate_id FROM v_candidate_agent_safe LIMIT 1" in combined_sql
    assert "SELECT candidate_id FROM v_candidate_agent_privileged LIMIT 1" in combined_sql
    assert "SELECT candidate_id FROM v_candidate_interview_safe LIMIT 1" in combined_sql
    assert "SELECT candidate_id FROM v_candidate_interview_evaluate_safe LIMIT 1" in combined_sql
    assert "SELECT candidate_id FROM v_candidate_interview_question_safe LIMIT 1" in combined_sql
    assert "SELECT candidate_id FROM v_candidate_screen_evaluate_safe LIMIT 1" in combined_sql


def test_mysql_repository_ready_fails_when_any_safe_view_is_missing(monkeypatch):
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            if "v_candidate_interview_question_safe" in sql:
                raise RuntimeError("view does not exist")

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def close(self):
            pass

    fake_pymysql = SimpleNamespace(
        connect=lambda **kwargs: FakeConnection(),
        cursors=SimpleNamespace(DictCursor=object),
    )
    monkeypatch.setitem(sys.modules, "pymysql", fake_pymysql)

    repo = MySQLTalentRepository({"host": "localhost", "user": "u", "password": "p", "database": "d"})

    assert repo.ready() is False
