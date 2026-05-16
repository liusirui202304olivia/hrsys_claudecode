"""数据访问层包。

该包包含 SQL dump 离线验证 repository 和 MySQL repository。
Repository 是唯一允许接触原始表字段和底层数据源的层，但只能接受受控 filter，不暴露自由 SQL。
向上返回的数据必须再经过服务层字段策略和权限过滤后才能给 Agent 使用。
"""

from hr_mcp.repositories.dump_repository import DumpTalentRepository
from hr_mcp.repositories.mysql_repository import MySQLTalentRepository
