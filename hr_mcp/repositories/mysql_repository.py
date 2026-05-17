"""MySQL 受控数据访问实现。

该文件封装线上 MySQL 访问路径，仅接受明确白名单 filter，并通过安全视图读取候选人数据。
它禁止自由 SQL 和未知 filter，避免调用方因为拼接条件或静默忽略参数导致越权查询。
Repository 返回的记录仍需经过 safe view service 和 field policy 后才能暴露给 MCP 工具。
"""

from typing import Any, Dict, List, Optional, Set, Tuple, Union


ALLOWED_CANDIDATE_FILTERS = {
    "position_query",
    "position_name",
    "position_id",
    "candidate_status",
    "status",
    "min_work_years",
    "skills_any",
    "experience_keywords_any",
}


class MySQLTalentRepository:
    SAFE_VIEW = "v_candidate_agent_safe"
    PRIVILEGED_VIEW = "v_candidate_agent_privileged"

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def ready(self) -> bool:
        try:
            import pymysql
            connection = pymysql.connect(
                host=self.config["host"],
                port=int(self.config.get("port", 3306)),
                user=self.config["user"],
                password=self.config["password"],
                database=self.config["database"],
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=3,
            )
            connection.close()
            return True
        except Exception:
            return False

    def search_candidates(self, filters: Optional[Dict[str, Any]], limit: int, include_privileged: bool = False) -> List[Dict[str, Any]]:
        filters = filters or {}
        where, params = self._where(filters)
        view_name = self._view(include_privileged)
        sql = f"""
            SELECT v.*
            FROM {view_name} v
            {where}
            ORDER BY v.update_time DESC
            LIMIT %s
        """
        params.append(max(0, min(int(limit), 10_000)))
        return self._fetch_all(sql, params)

    def get_candidates_by_ids(self, candidate_ids: List[Union[int, str]], include_privileged: bool = False) -> List[Dict[str, Any]]:
        if not candidate_ids:
            return []
        placeholders = ",".join(["%s"] * len(candidate_ids))
        view_name = self._view(include_privileged)
        sql = f"""
            SELECT v.*
            FROM {view_name} v
            WHERE v.candidate_id IN ({placeholders})
        """
        return self._fetch_all(sql, list(candidate_ids))

    def count_candidates(self, filters: Optional[Dict[str, Any]]) -> int:
        return len(self.search_candidates(filters or {}, 10_000))

    def position_distribution(self, filters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self._distribution("position_name", filters or {})

    def status_distribution(self, filters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self._distribution("status", filters or {})

    def source_distribution(self, filters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self._distribution("source_name", filters or {})

    def _where(self, filters: Dict[str, Any]) -> Tuple[str, List[Any]]:
        self._validate_filters(filters)
        where: List[str] = []
        params: List[Any] = []
        position_query = filters.get("position_query") or filters.get("position_name")
        if position_query:
            where.append("v.position_name LIKE %s")
            params.append(f"%{position_query}%")
        if filters.get("position_id") is not None:
            where.append("v.position_id = %s")
            params.append(int(filters["position_id"]))
        if filters.get("min_work_years") is not None:
            where.append("v.work_years >= %s")
            params.append(int(filters["min_work_years"]))
        statuses = filters.get("candidate_status", filters.get("status"))
        if statuses:
            status_list = [statuses] if isinstance(statuses, str) else list(statuses)
            where.append("v.status IN (" + ",".join(["%s"] * len(status_list)) + ")")
            params.extend(status_list)
        keywords = list(filters.get("skills_any") or []) + list(filters.get("experience_keywords_any") or [])
        for keyword in keywords:
            where.append("(v.skills LIKE %s OR v.experiences LIKE %s OR v.project_experiences LIKE %s)")
            like_value = f"%{keyword}%"
            params.extend([like_value, like_value, like_value])
        return ("WHERE " + " AND ".join(where) if where else ""), params

    def _validate_filters(self, filters: Dict[str, Any]) -> None:
        unknown = sorted(set(filters) - ALLOWED_CANDIDATE_FILTERS)
        if unknown:
            raise ValueError(f"Unsupported candidate filters: {', '.join(unknown)}")

    def _distribution(self, field: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        counts: Dict[str, int] = {}
        for row in self.search_candidates(filters, 10_000):
            key = row.get(field) or "UNKNOWN"
            counts[key] = counts.get(key, 0) + 1
        return [{field: key, "count": value} for key, value in counts.items()]

    def _fetch_all(self, sql: str, params: List[Any]) -> List[Dict[str, Any]]:
        import pymysql
        connection = pymysql.connect(
            host=self.config["host"],
            port=int(self.config.get("port", 3306)),
            user=self.config["user"],
            password=self.config["password"],
            database=self.config["database"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return list(cursor.fetchall())
        finally:
            connection.close()

    def _view(self, include_privileged: bool) -> str:
        return self.PRIVILEGED_VIEW if include_privileged else self.SAFE_VIEW
