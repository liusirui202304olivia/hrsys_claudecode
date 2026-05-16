from __future__ import annotations

from typing import Any


class MySQLTalentRepository:
    def __init__(self, config: dict[str, Any]):
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

    def search_candidates(self, filters: dict[str, Any] | None, limit: int) -> list[dict[str, Any]]:
        filters = filters or {}
        where: list[str] = []
        params: list[Any] = []
        if filters.get("position_query"):
            where.append("p.name LIKE %s")
            params.append(f"%{filters['position_query']}%")
        if filters.get("min_work_years") is not None:
            where.append("c.work_years >= %s")
            params.append(int(filters["min_work_years"]))
        statuses = filters.get("candidate_status", filters.get("status"))
        if statuses:
            status_list = [statuses] if isinstance(statuses, str) else list(statuses)
            where.append("c.status IN (" + ",".join(["%s"] * len(status_list)) + ")")
            params.extend(status_list)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        sql = f"""
            SELECT c.*, p.name AS position_name, p.category AS position_category,
                   p.jd AS position_jd, p.is_active AS position_is_active,
                   s.name AS source_name, s.full_name AS source_full_name
            FROM hr_candidate c
            LEFT JOIN hr_position p ON p.id = c.position_id
            LEFT JOIN hr_source s ON s.id = c.source_id
            {where_sql}
            ORDER BY c.update_time DESC
            LIMIT %s
        """
        params.append(max(0, min(int(limit), 10_000)))
        return self._fetch_all(sql, params)

    def get_candidates_by_ids(self, candidate_ids: list[int | str]) -> list[dict[str, Any]]:
        if not candidate_ids:
            return []
        placeholders = ",".join(["%s"] * len(candidate_ids))
        sql = f"""
            SELECT c.*, p.name AS position_name, p.category AS position_category,
                   p.jd AS position_jd, p.is_active AS position_is_active,
                   s.name AS source_name, s.full_name AS source_full_name
            FROM hr_candidate c
            LEFT JOIN hr_position p ON p.id = c.position_id
            LEFT JOIN hr_source s ON s.id = c.source_id
            WHERE c.id IN ({placeholders})
        """
        return self._fetch_all(sql, list(candidate_ids))

    def count_candidates(self, filters: dict[str, Any] | None) -> int:
        return len(self.search_candidates(filters or {}, 10_000))

    def position_distribution(self, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
        return self._distribution("position_name", filters or {})

    def status_distribution(self, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
        return self._distribution("status", filters or {})

    def source_distribution(self, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
        return self._distribution("source_name", filters or {})

    def _distribution(self, field: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for row in self.search_candidates(filters, 10_000):
            key = row.get(field) or "UNKNOWN"
            counts[key] = counts.get(key, 0) + 1
        return [{field: key, "count": value} for key, value in counts.items()]

    def _fetch_all(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
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
