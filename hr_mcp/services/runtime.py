"""运行时依赖装配服务。

该文件负责根据配置组装 repository、安全策略、各业务服务、工具注册、工具路由和审计/结果存储。
它是 HTTP app 与业务服务之间的组合根，避免在 HTTP 层散落依赖创建逻辑。
除装配和 readiness 检查外，本文件不实现具体招聘业务规则。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hr_mcp.repositories.dump_repository import DumpTalentRepository
from hr_mcp.repositories.mysql_repository import MySQLTalentRepository
from hr_mcp.security.field_policy import FieldPolicy
from hr_mcp.services.audit_trace_service import AuditTraceService
from hr_mcp.services.candidate_retrieval_service import CandidateRetrievalService
from hr_mcp.services.candidate_safe_view_service import CandidateSafeViewService
from hr_mcp.services.config_center import ConfigCenter
from hr_mcp.services.permission_service import PermissionService
from hr_mcp.services.report_generation_service import ReportGenerationService
from hr_mcp.services.screening_policy_service import ScreeningPolicyService
from hr_mcp.services.screening_result_store import ScreeningResultStore
from hr_mcp.services.talent_analysis_service import TalentAnalysisService
from hr_mcp.services.talent_pool_query_service import TalentPoolQueryService
from hr_mcp.services.tool_registry import ToolRegistry
from hr_mcp.services.tool_router import ToolRouter


@dataclass
class RuntimeContainer:
    config: ConfigCenter
    repository: Any
    router: ToolRouter

    def ready_checks(self) -> dict[str, bool]:
        return {
            "database": bool(self.repository.ready()),
            "standard_markdown": self.config.standard_markdown_dir.exists(),
            "audit_store": self._path_available(self.config.audit_path.parent),
        }

    def read_audit_records(self, limit: int = 100) -> list[dict[str, Any]]:
        path = self.config.audit_path
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
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


def build_runtime(config: ConfigCenter | None = None) -> RuntimeContainer:
    config = config or ConfigCenter()
    repository = _build_repository(config)
    field_policy = FieldPolicy()
    permission_service = PermissionService()
    safe_view_service = CandidateSafeViewService(field_policy, permission_service)
    retrieval_service = CandidateRetrievalService(repository, safe_view_service)
    talent_query_service = TalentPoolQueryService(repository, safe_view_service)
    policy_service = ScreeningPolicyService(config.policy_dir, config.standard_markdown_dir)
    analysis_service = TalentAnalysisService(repository, safe_view_service)
    report_service = ReportGenerationService()
    result_store = ScreeningResultStore(config.result_path)
    audit_service = AuditTraceService(config.audit_path)
    router = ToolRouter(
        registry=ToolRegistry(),
        policy_service=policy_service,
        retrieval_service=retrieval_service,
        talent_query_service=talent_query_service,
        analysis_service=analysis_service,
        report_service=report_service,
        result_store=result_store,
        audit_service=audit_service,
    )
    return RuntimeContainer(config=config, repository=repository, router=router)


def _build_repository(config: ConfigCenter):
    if config.data_backend == "mysql":
        return MySQLTalentRepository(config.mysql_config)
    return DumpTalentRepository(config.dump_path)
