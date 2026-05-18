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
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='候选人';
INSERT INTO `hr_candidate` VALUES
(1,10,20,'SCREEN_PROCESS',2,'张三','MALE','BACHELOR','BACHELOR','四川大学','计算机',5,'[{"company":"华为","position":"C++工程师"}]','2026-06-01','[{"project":"CPU模型","content":"负责gem5性能建模"}]','["C++","gem5"]'),
(2,10,21,'REJECTED',3,'李四','FEMALE','BACHELOR','BACHELOR','电子科大','软件工程',1,'[]',NULL,'[]','["Java"]');

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
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='面试';
INSERT INTO `hr_interview` VALUES
(100,1,'技术一面'),
(101,1,'技术二面'),
(102,2,'HR面');

CREATE TABLE `hr_interview_evaluate` (
  `id` int NOT NULL AUTO_INCREMENT,
  `interview_id` int NOT NULL COMMENT '面试ID',
  `interviewer_id` int NOT NULL COMMENT '面试官ID',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='面试评价';
INSERT INTO `hr_interview_evaluate` VALUES
(1000,100,42),
(1001,101,43),
(1002,102,99);
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


def test_dump_repository_computes_position_distribution(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    distribution = repo.position_distribution({})

    assert distribution == [
        {"position_name": "应用软件开发工程师", "count": 1},
        {"position_name": "芯片建模工程师", "count": 1},
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
    stale = repo.search_candidates({"status_updated_before": "2025-12-01"}, page_size=10)

    assert [row["name"] for row in active["items"]] == ["流程中候选人"]
    assert [row["name"] for row in old_rejected["items"]] == ["历史拒绝候选人"]
    assert [row["name"] for row in recent_rejected["items"]] == ["近期拒绝候选人"]
    assert [row["name"] for row in hired["items"]] == ["已入职候选人"]
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


def test_mysql_repository_recruiter_scope_uses_aggregated_follower_ids():
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

    repo.search_candidates({}, page_size=10, identity_scope={"role": "RECRUITER", "user_id": 42})
    combined_sql = "\n".join(repo.sqls)

    assert "FIND_IN_SET(%s, COALESCE(v.follower_ids, ''))" in combined_sql
    assert re.search(r"\bv\.follower_id\b", combined_sql) is None
    assert repo.params_list[0][:2] == [42, 42]


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


def test_mysql_repository_ready_checks_both_candidate_views(monkeypatch):
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


def test_mysql_repository_ready_fails_when_any_candidate_view_is_missing(monkeypatch):
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            if "v_candidate_agent_privileged" in sql:
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
