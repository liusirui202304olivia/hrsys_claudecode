"""MySQL 受控数据访问实现。

该文件封装线上 MySQL 访问路径，仅接受明确白名单 filter，并通过安全视图读取候选人数据。
它禁止自由 SQL 和未知 filter，避免调用方因为拼接条件或静默忽略参数导致越权查询。
Repository 返回的记录仍需经过 safe view service 和 field policy 后才能暴露给 MCP 工具。
"""

import base64
import json
from datetime import date, datetime, timedelta
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
    "candidate_pool",
    "rejected_before_days",
    "status_updated_before",
    "status_updated_after",
}

VALID_CANDIDATE_POOLS = {"active", "old_rejected", "recent_rejected", "hired"}
DEFAULT_REJECTED_BEFORE_DAYS = 180


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
            try:
                with connection.cursor() as cursor:
                    for view_name in [self.SAFE_VIEW, self.PRIVILEGED_VIEW]:
                        cursor.execute(f"SELECT candidate_id FROM {view_name} LIMIT 1")
            finally:
                connection.close()
            return True
        except Exception:
            return False

    def search_candidates(
        self,
        filters: Optional[Dict[str, Any]],
        page_size: int,
        cursor: Optional[str] = None,
        include_privileged: bool = False,
        identity_scope: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        filters = filters or {}
        page_size = self._validate_page_size(page_size)
        where_parts, params = self._where_parts(filters, identity_scope)
        cursor_sql, cursor_params = self._cursor_condition(cursor)
        if cursor_sql:
            where_parts.append(cursor_sql)
            params.extend(cursor_params)
        where = self._where_sql(where_parts)
        view_name = self._view(include_privileged)
        sql = f"""
            SELECT v.*
            FROM {view_name} v
            {where}
            ORDER BY COALESCE(v.update_time, '1970-01-01 00:00:00') DESC, v.candidate_id DESC
            LIMIT %s
        """
        params.append(page_size + 1)
        rows = self._fetch_all(sql, params)
        items = rows[:page_size]
        return {
            "items": items,
            "total_count": self.count_candidates(filters, include_privileged=include_privileged, identity_scope=identity_scope),
            "has_more": len(rows) > page_size,
            "next_cursor": self._encode_cursor(items[-1]) if len(rows) > page_size and items else None,
        }

    def get_candidates_by_ids(
        self,
        candidate_ids: List[Union[int, str]],
        include_privileged: bool = False,
        identity_scope: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not candidate_ids:
            return []
        placeholders = ",".join(["%s"] * len(candidate_ids))
        where_parts, params = self._scope_where_parts(identity_scope)
        where_parts.insert(0, f"v.candidate_id IN ({placeholders})")
        params = list(candidate_ids) + params
        view_name = self._view(include_privileged)
        sql = f"""
            SELECT v.*
            FROM {view_name} v
            {self._where_sql(where_parts)}
        """
        return self._fetch_all(sql, params)

    def count_candidates(
        self,
        filters: Optional[Dict[str, Any]],
        include_privileged: bool = False,
        identity_scope: Optional[Dict[str, Any]] = None,
    ) -> int:
        where_parts, params = self._where_parts(filters or {}, identity_scope)
        sql = f"""
            SELECT COUNT(*) AS total_count
            FROM {self._view(include_privileged)} v
            {self._where_sql(where_parts)}
        """
        rows = self._fetch_all(sql, params)
        return int((rows[0] or {}).get("total_count") or 0) if rows else 0

    def position_distribution(self, filters: Optional[Dict[str, Any]], identity_scope: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return self._distribution("position_name", filters or {}, identity_scope)

    def status_distribution(self, filters: Optional[Dict[str, Any]], identity_scope: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return self._distribution("status", filters or {}, identity_scope)

    def source_distribution(self, filters: Optional[Dict[str, Any]], identity_scope: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return self._distribution("source_name", filters or {}, identity_scope)

    def _where_parts(self, filters: Dict[str, Any], identity_scope: Optional[Dict[str, Any]] = None) -> Tuple[List[str], List[Any]]:
        self._validate_filters(filters)
        where, params = self._scope_where_parts(identity_scope)
        where = list(where)
        params = list(params)
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
        candidate_pool = filters.get("candidate_pool")
        if candidate_pool == "active":
            where.append("v.status NOT IN ('REJECTED', 'HIRED')")
        elif candidate_pool == "old_rejected":
            where.append("v.status = %s AND v.update_time <= %s")
            params.extend(["REJECTED", self._rejected_cutoff(filters)])
        elif candidate_pool == "recent_rejected":
            where.append("v.status = %s AND v.update_time > %s")
            params.extend(["REJECTED", self._rejected_cutoff(filters)])
        elif candidate_pool == "hired":
            where.append("v.status = %s")
            params.append("HIRED")
        if filters.get("status_updated_before") is not None:
            where.append("v.update_time <= %s")
            params.append(self._format_day_end(filters["status_updated_before"], "status_updated_before"))
        if filters.get("status_updated_after") is not None:
            where.append("v.update_time >= %s")
            params.append(self._format_day_start(filters["status_updated_after"], "status_updated_after"))
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
        return where, params

    def _scope_where_parts(self, identity_scope: Optional[Dict[str, Any]]) -> Tuple[List[str], List[Any]]:
        scope = identity_scope or {}
        if scope.get("deny_all"):
            return ["1 = 0"], []
        role = scope.get("role")
        if role == "RECRUITER":
            return ["(v.hr_id = %s OR FIND_IN_SET(%s, COALESCE(v.follower_ids, '')))"], [scope.get("user_id"), scope.get("user_id")]
        if role == "DEPARTMENT_MANAGER":
            return ["v.proposed_department_id = %s"], [scope.get("department_id")]
        if role == "INTERVIEWER":
            return ["FIND_IN_SET(%s, COALESCE(v.interviewer_ids, ''))"], [scope.get("user_id")]
        return [], []

    def _where_sql(self, where_parts: List[str]) -> str:
        return "WHERE " + " AND ".join(where_parts) if where_parts else ""

    def _validate_filters(self, filters: Dict[str, Any]) -> None:
        unknown = sorted(set(filters) - ALLOWED_CANDIDATE_FILTERS)
        if unknown:
            raise ValueError(f"Unsupported candidate filters: {', '.join(unknown)}")
        self._validate_candidate_pool_filters(filters)

    def _distribution(self, field: str, filters: Dict[str, Any], identity_scope: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        where_parts, params = self._where_parts(filters or {}, identity_scope)
        sql = f"""
            SELECT COALESCE(v.{field}, 'UNKNOWN') AS {field}, COUNT(*) AS count
            FROM {self.SAFE_VIEW} v
            {self._where_sql(where_parts)}
            GROUP BY v.{field}
            ORDER BY count DESC, v.{field} ASC
        """
        return self._fetch_all(sql, params)

    def _validate_page_size(self, page_size: int) -> int:
        try:
            value = int(page_size)
        except (TypeError, ValueError):
            raise ValueError("page_size must be an integer")
        if value < 1:
            raise ValueError("page_size must be greater than 0")
        return value

    def _validate_candidate_pool_filters(self, filters: Dict[str, Any]) -> None:
        candidate_pool = filters.get("candidate_pool")
        if candidate_pool is not None and candidate_pool not in VALID_CANDIDATE_POOLS:
            raise ValueError("candidate_pool must be one of active, old_rejected, recent_rejected, hired")
        if candidate_pool is not None and (filters.get("status") is not None or filters.get("candidate_status") is not None):
            raise ValueError("candidate_pool cannot be combined with status or candidate_status")
        if "rejected_before_days" in filters:
            self._validate_positive_integer(filters.get("rejected_before_days"), "rejected_before_days")
        for key in ["status_updated_before", "status_updated_after"]:
            if key in filters and filters.get(key) is not None:
                self._parse_yyyy_mm_dd(filters.get(key), key)

    def _rejected_cutoff(self, filters: Dict[str, Any]) -> str:
        days = filters.get("rejected_before_days", DEFAULT_REJECTED_BEFORE_DAYS)
        days = self._validate_positive_integer(days, "rejected_before_days")
        cutoff_date = date.today() - timedelta(days=days)
        return f"{cutoff_date.isoformat()} 23:59:59"

    def _format_day_start(self, value: Any, name: str) -> str:
        return f"{self._parse_yyyy_mm_dd(value, name).date().isoformat()} 00:00:00"

    def _format_day_end(self, value: Any, name: str) -> str:
        return f"{self._parse_yyyy_mm_dd(value, name).date().isoformat()} 23:59:59"

    def _parse_yyyy_mm_dd(self, value: Any, name: str) -> datetime:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be YYYY-MM-DD")
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"{name} must be YYYY-MM-DD")

    def _validate_positive_integer(self, value: Any, name: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a positive integer")
        try:
            integer_value = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be a positive integer")
        if integer_value < 1:
            raise ValueError(f"{name} must be a positive integer")
        return integer_value

    def _cursor_condition(self, cursor: Optional[str]) -> Tuple[str, List[Any]]:
        if not cursor:
            return "", []
        payload = self._decode_cursor(cursor)
        update_time = payload.get("update_time")
        candidate_id = payload.get("candidate_id")
        if not update_time or candidate_id is None:
            raise ValueError("Invalid cursor")
        sort_expr = "COALESCE(v.update_time, '1970-01-01 00:00:00')"
        return (
            f"({sort_expr} < %s OR ({sort_expr} = %s AND v.candidate_id < %s))",
            [update_time, update_time, candidate_id],
        )

    def _encode_cursor(self, row: Dict[str, Any]) -> Optional[str]:
        candidate_id = row.get("candidate_id") or row.get("id")
        if candidate_id is None:
            return None
        update_time = row.get("update_time") or "1970-01-01 00:00:00"
        if isinstance(update_time, datetime):
            update_time = update_time.isoformat(sep=" ")
        elif isinstance(update_time, date):
            update_time = update_time.isoformat()
        payload = {"update_time": str(update_time), "candidate_id": int(candidate_id)}
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def _decode_cursor(self, cursor: str) -> Dict[str, Any]:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
            payload = json.loads(raw)
        except Exception:
            raise ValueError("Invalid cursor")
        if not isinstance(payload, dict):
            raise ValueError("Invalid cursor")
        return payload

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
