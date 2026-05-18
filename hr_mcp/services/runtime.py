"""运行时依赖装配服务。

该文件负责根据配置组装 repository、安全策略、数据服务、工具注册、工具路由和审计/结果存储。
它是 HTTP app 与安全数据服务之间的组合根，避免在 HTTP 层散落依赖创建逻辑。
本文件不装配岗位标准读取、候选人推荐、招聘分析或报告生成等 Agent 业务推理能力。
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from hr_mcp.repositories.dump_repository import DumpTalentRepository
from hr_mcp.repositories.mysql_repository import MySQLTalentRepository
from hr_mcp.security.field_policy import FieldPolicy
from hr_mcp.services.audit_trace_service import AuditTraceService
from hr_mcp.services.candidate_retrieval_service import CandidateRetrievalService
from hr_mcp.services.candidate_safe_view_service import CandidateSafeViewService
from hr_mcp.services.config_center import ConfigCenter
from hr_mcp.services.permission_service import PermissionService
from hr_mcp.services.screening_result_store import ScreeningResultStore
from hr_mcp.services.safe_sql_service import SafeSqlService
from hr_mcp.services.talent_pool_query_service import TalentPoolQueryService
from hr_mcp.services.tool_registry import ToolRegistry
from hr_mcp.services.tool_router import ToolRouter


@dataclass
class RuntimeContainer:
    config: ConfigCenter
    repository: Any
    router: ToolRouter

    def ready_checks(self) -> Dict[str, bool]:
        return {
            "database": bool(self.repository.ready()),
            "audit_store": self._path_available(self.config.audit_path.parent),
        }

    def read_audit_records(self, limit: int = 100) -> List[Dict[str, Any]]:
        path = self.config.audit_path
        if not path.exists():
            return []
        records: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            if line.strip():
                records.append(json.loads(line))
        return records

    def _path_available(self, path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path.exists()
        except OSError:
            return False


def build_runtime(config: Optional[ConfigCenter] = None) -> RuntimeContainer:
    config = config or ConfigCenter()
    repository = _build_repository(config)
    field_policy = FieldPolicy.from_yaml(config.field_policy_path)
    permission_service = PermissionService()
    safe_view_service = CandidateSafeViewService(field_policy, permission_service)
    retrieval_service = CandidateRetrievalService(repository, safe_view_service)
    talent_query_service = TalentPoolQueryService(repository, safe_view_service)
    safe_sql_service = SafeSqlService(repository, field_policy)
    result_store = ScreeningResultStore(config.result_path)
    audit_service = AuditTraceService(config.audit_path)
    router = ToolRouter(
        registry=ToolRegistry(),
        retrieval_service=retrieval_service,
        talent_query_service=talent_query_service,
        safe_sql_service=safe_sql_service,
        result_store=result_store,
        audit_service=audit_service,
    )
    return RuntimeContainer(config=config, repository=repository, router=router)


def _build_repository(config: ConfigCenter):
    backend = config.data_backend
    if backend == "mysql":
        return MySQLTalentRepository(config.mysql_config)
    if backend == "dump":
        return DumpTalentRepository(config.dump_path)
    raise ValueError("Unsupported HR_DATA_BACKEND: " + backend)
