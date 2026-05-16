from pathlib import Path

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
'''


def write_dump(tmp_path: Path) -> Path:
    dump_path = tmp_path / "sample.sql"
    dump_path.write_text(SAMPLE_DUMP, encoding="utf-8")
    return dump_path


def test_dump_repository_parses_schema_and_joined_rows(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    candidates = repo.search_candidates({"position_query": "芯片建模"}, limit=10)

    assert len(candidates) == 1
    assert candidates[0]["id"] == 1
    assert candidates[0]["name"] == "张三"
    assert candidates[0]["position_name"] == "芯片建模工程师"
    assert candidates[0]["source_name"] == "历史导入"


def test_dump_repository_filters_status_keyword_and_work_years(tmp_path: Path):
    repo = DumpTalentRepository(write_dump(tmp_path))

    candidates = repo.search_candidates(
        {
            "status": ["SCREEN_PROCESS"],
            "skills_any": ["gem5"],
            "min_work_years": 3,
        },
        limit=10,
    )

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
        repo.search_candidates({"free_sql": "status = 'x'"}, limit=10)


def test_mysql_repository_uses_safe_view_not_raw_candidate_star():
    source = inspect.getsource(MySQLTalentRepository)

    assert "v_candidate_agent_privileged" in source
    assert "SELECT c.*" not in source
