"""SQL dump 离线数据访问实现。

该文件解析内网导出的 SQL dump，提取核心招聘表并生成候选人、岗位、来源的联表视图。
它用于 P0 本地验证和测试，支持受控 filter、候选人详情读取和聚合分布计算。
该层会读取原始字段，但不会直接决定 Agent 可见字段；安全投影由服务层完成。
"""

import base64
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
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


class DumpTalentRepository:
    def __init__(self, dump_path: Union[str, Path]):
        self.dump_path = Path(dump_path)
        self._columns: Optional[Dict[str, List[str]]] = None
        self._tables: Optional[Dict[str, List[Dict[str, Any]]]] = None

    def ready(self) -> bool:
        return self.dump_path.exists()

    def table(self, table_name: str) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        assert self._tables is not None
        return self._tables.get(table_name, [])

    def search_candidates(
        self,
        filters: Optional[Dict[str, Any]],
        page_size: int,
        cursor: Optional[str] = None,
        include_privileged: bool = False,
        identity_scope: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        filters = filters or {}
        self._validate_filters(filters)
        page_size = self._validate_page_size(page_size)
        rows = [row for row in self._joined_candidates() if self._candidate_matches(row, filters)]
        rows = self._apply_scope(rows, identity_scope)
        rows = self._sort_rows(rows)
        if cursor:
            rows = self._rows_after_cursor(rows, cursor)
        total_count = len(self._apply_scope(
            [row for row in self._joined_candidates() if self._candidate_matches(row, filters)],
            identity_scope,
        ))
        page_rows = rows[:page_size]
        return {
            "items": page_rows,
            "total_count": total_count,
            "has_more": len(rows) > page_size,
            "next_cursor": self._encode_cursor(page_rows[-1]) if len(rows) > page_size and page_rows else None,
        }

    def get_candidates_by_ids(
        self,
        candidate_ids: List[Union[int, str]],
        include_privileged: bool = False,
        identity_scope: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        ids = {str(candidate_id) for candidate_id in candidate_ids}
        rows = [row for row in self._joined_candidates() if str(row.get("id")) in ids or str(row.get("candidate_id")) in ids]
        return self._apply_scope(rows, identity_scope)

    def count_candidates(
        self,
        filters: Optional[Dict[str, Any]],
        include_privileged: bool = False,
        identity_scope: Optional[Dict[str, Any]] = None,
    ) -> int:
        filters = filters or {}
        self._validate_filters(filters)
        rows = [row for row in self._joined_candidates() if self._candidate_matches(row, filters)]
        return len(self._apply_scope(rows, identity_scope))

    def position_distribution(self, filters: Optional[Dict[str, Any]], identity_scope: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        counts: Dict[str, int] = {}
        for row in self._aggregate_rows(filters or {}, identity_scope):
            key = row.get("position_name") or "UNKNOWN"
            counts[key] = counts.get(key, 0) + 1
        return [
            {"position_name": key, "count": count}
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def status_distribution(self, filters: Optional[Dict[str, Any]], identity_scope: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        counts: Dict[str, int] = {}
        for row in self._aggregate_rows(filters or {}, identity_scope):
            key = row.get("status") or "UNKNOWN"
            counts[key] = counts.get(key, 0) + 1
        return [
            {"status": key, "count": count}
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def source_distribution(self, filters: Optional[Dict[str, Any]], identity_scope: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        counts: Dict[str, int] = {}
        for row in self._aggregate_rows(filters or {}, identity_scope):
            key = row.get("source_name") or "UNKNOWN"
            counts[key] = counts.get(key, 0) + 1
        return [
            {"source_name": key, "count": count}
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def _validate_filters(self, filters: Dict[str, Any]) -> None:
        unknown = sorted(set(filters) - ALLOWED_CANDIDATE_FILTERS)
        if unknown:
            raise ValueError(f"Unsupported candidate filters: {', '.join(unknown)}")
        self._validate_candidate_pool_filters(filters)

    def _aggregate_rows(self, filters: Dict[str, Any], identity_scope: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self._validate_filters(filters)
        rows = [row for row in self._joined_candidates() if self._candidate_matches(row, filters)]
        return self._apply_scope(rows, identity_scope)

    def _apply_scope(self, rows: List[Dict[str, Any]], identity_scope: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scope = identity_scope or {}
        if scope.get("deny_all"):
            return []
        role = scope.get("role")
        if role == "RECRUITER":
            user_id = scope.get("user_id")
            return [row for row in rows if row.get("hr_id") == user_id or self._follower_matches(row, user_id)]
        if role == "DEPARTMENT_MANAGER":
            department_id = scope.get("department_id")
            return [row for row in rows if row.get("proposed_department_id") == department_id]
        if role == "INTERVIEWER":
            user_id = str(scope.get("user_id"))
            return [row for row in rows if user_id in {str(item) for item in row.get("interviewer_ids", [])}]
        return list(rows)

    def _validate_page_size(self, page_size: int) -> int:
        try:
            value = int(page_size)
        except (TypeError, ValueError):
            raise ValueError("page_size must be an integer")
        if value < 1:
            raise ValueError("page_size must be greater than 0")
        return value

    def _sort_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(rows, key=lambda row: (str(row.get("update_time") or ""), int(row.get("candidate_id") or row.get("id") or 0)), reverse=True)

    def _rows_after_cursor(self, rows: List[Dict[str, Any]], cursor: str) -> List[Dict[str, Any]]:
        payload = self._decode_cursor(cursor)
        cursor_key = (str(payload.get("update_time") or ""), int(payload.get("candidate_id") or 0))
        return [
            row for row in rows
            if (str(row.get("update_time") or ""), int(row.get("candidate_id") or row.get("id") or 0)) < cursor_key
        ]

    def _encode_cursor(self, row: Dict[str, Any]) -> Optional[str]:
        candidate_id = row.get("candidate_id") or row.get("id")
        if candidate_id is None:
            return None
        update_time = row.get("update_time") or ""
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

    def _ensure_loaded(self) -> None:
        if self._tables is not None:
            return
        text = self.dump_path.read_text(encoding="utf-8", errors="replace")
        self._columns = self._parse_columns(text)
        self._tables = {}
        for table_name, columns in self._columns.items():
            rows = self._iter_insert_rows(text, table_name)
            self._tables[table_name] = [dict(zip(columns, row)) for row in rows]

    def _parse_columns(self, text: str) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for match in re.finditer(r"CREATE TABLE `([^`]+)` \((.*?)\) ENGINE=", text, re.S):
            table_name = match.group(1)
            columns: List[str] = []
            for line in match.group(2).splitlines():
                stripped = line.strip()
                if stripped.startswith("`"):
                    columns.append(stripped.split("`", 2)[1])
            result[table_name] = columns
        return result

    def _iter_insert_rows(self, text: str, table_name: str) -> List[List[Any]]:
        rows: List[List[Any]] = []
        pattern = re.compile(r"INSERT INTO `" + re.escape(table_name) + r"` VALUES")
        for match in pattern.finditer(text):
            i = match.end()
            depth = 0
            in_string = False
            escaped = False
            field = ""
            row: List[str] = []
            while i < len(text):
                char = text[i]
                if in_string:
                    field += char
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == "'":
                        in_string = False
                else:
                    if char == "'":
                        in_string = True
                        field += char
                    elif char == "(":
                        if depth > 0:
                            field += char
                        depth += 1
                    elif char == ")":
                        depth -= 1
                        if depth == 0:
                            row.append(field.strip())
                            rows.append([self._clean_sql_value(value) for value in row])
                            row = []
                            field = ""
                        else:
                            field += char
                    elif char == "," and depth == 1:
                        row.append(field.strip())
                        field = ""
                    elif char == ";" and depth == 0:
                        break
                    elif depth >= 1:
                        field += char
                i += 1
        return rows

    def _clean_sql_value(self, raw: str) -> Any:
        value = raw.strip()
        if value.upper() == "NULL":
            return None
        if value.startswith("'") and value.endswith("'"):
            unquoted = value[1:-1]
            return unquoted.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
        if re.fullmatch(r"-?\d+", value):
            return int(value)
        return value

    def _joined_candidates(self) -> List[Dict[str, Any]]:
        positions = {row.get("id"): row for row in self.table("hr_position")}
        sources = {row.get("id"): row for row in self.table("hr_source")}
        follower_ids = self._follower_ids_by_candidate()
        interviewer_ids = self._interviewer_ids_by_candidate()
        joined: List[Dict[str, Any]] = []
        for candidate in self.table("hr_candidate"):
            row = dict(candidate)
            position = positions.get(candidate.get("position_id"), {})
            source = sources.get(candidate.get("source_id"), {})
            row["candidate_id"] = candidate.get("id")
            row["position_name"] = position.get("name")
            row["position_category"] = position.get("category")
            row["position_jd"] = position.get("jd")
            row["position_is_active"] = position.get("is_active")
            row["source_name"] = source.get("name")
            row["source_full_name"] = source.get("full_name")
            row["follower_ids"] = follower_ids.get(candidate.get("id"), [])
            row["interviewer_ids"] = interviewer_ids.get(candidate.get("id"), [])
            joined.append(row)
        return joined

    def _follower_ids_by_candidate(self) -> Dict[Any, List[Any]]:
        result: Dict[Any, Set[Any]] = {}
        for follower in self.table("hr_candidate_follower"):
            if not follower.get("is_current"):
                continue
            candidate_id = follower.get("candidate_id")
            follower_id = follower.get("follower_id")
            if candidate_id is None or follower_id is None:
                continue
            result.setdefault(candidate_id, set()).add(follower_id)
        return {candidate_id: sorted(followers) for candidate_id, followers in result.items()}

    def _interviewer_ids_by_candidate(self) -> Dict[Any, List[Any]]:
        result: Dict[Any, Set[Any]] = {}
        interview_candidate = {interview.get("id"): interview.get("candidate_id") for interview in self.table("hr_interview")}
        for evaluation in self.table("hr_interview_evaluate"):
            candidate_id = interview_candidate.get(evaluation.get("interview_id"))
            interviewer_id = evaluation.get("interviewer_id")
            if candidate_id is None or interviewer_id is None:
                continue
            result.setdefault(candidate_id, set()).add(interviewer_id)
        for interview in self.table("hr_interview"):
            candidate_id = interview.get("candidate_id")
            interviewer_id = interview.get("interviewer_id")
            if candidate_id is None or interviewer_id is None:
                continue
            result.setdefault(candidate_id, set()).add(interviewer_id)
        return {candidate_id: sorted(interviewers) for candidate_id, interviewers in result.items()}

    def _candidate_matches(self, row: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        if not self._candidate_pool_matches(row, filters):
            return False
        if not self._status_update_date_matches(row, filters):
            return False
        position_query = filters.get("position_query") or filters.get("position_name")
        if position_query and str(position_query) not in str(row.get("position_name") or ""):
            return False
        if filters.get("position_id") is not None and row.get("position_id") != filters.get("position_id"):
            return False
        statuses = filters.get("candidate_status", filters.get("status"))
        if statuses:
            status_set = {statuses} if isinstance(statuses, str) else set(statuses)
            if row.get("status") not in status_set:
                return False
        if filters.get("min_work_years") is not None:
            work_years = row.get("work_years")
            if work_years is None or int(work_years) < int(filters["min_work_years"]):
                return False
        keywords = list(filters.get("skills_any") or []) + list(filters.get("experience_keywords_any") or [])
        if keywords:
            haystack = self._search_text(row)
            if not any(str(keyword).lower() in haystack for keyword in keywords):
                return False
        return True

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

    def _candidate_pool_matches(self, row: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        candidate_pool = filters.get("candidate_pool")
        if not candidate_pool:
            return True
        status = row.get("status")
        if candidate_pool == "active":
            return status not in {"REJECTED", "HIRED"}
        if candidate_pool == "hired":
            return status == "HIRED"
        if status != "REJECTED":
            return False
        cutoff = self._rejected_cutoff(filters)
        update_time = self._row_update_time(row)
        if update_time is None:
            return False
        if candidate_pool == "old_rejected":
            return update_time <= cutoff
        if candidate_pool == "recent_rejected":
            return update_time > cutoff
        return True

    def _status_update_date_matches(self, row: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        if filters.get("status_updated_before") is None and filters.get("status_updated_after") is None:
            return True
        update_time = self._row_update_time(row)
        if filters.get("status_updated_before") is not None:
            before = self._parse_yyyy_mm_dd(filters["status_updated_before"], "status_updated_before").replace(hour=23, minute=59, second=59)
            if update_time is None or update_time > before:
                return False
        if filters.get("status_updated_after") is not None:
            after = self._parse_yyyy_mm_dd(filters["status_updated_after"], "status_updated_after")
            if update_time is None or update_time < after:
                return False
        return True

    def _rejected_cutoff(self, filters: Dict[str, Any]) -> datetime:
        days = filters.get("rejected_before_days", DEFAULT_REJECTED_BEFORE_DAYS)
        days = self._validate_positive_integer(days, "rejected_before_days")
        cutoff_date = date.today() - timedelta(days=days)
        return datetime(cutoff_date.year, cutoff_date.month, cutoff_date.day, 23, 59, 59)

    def _row_update_time(self, row: Dict[str, Any]) -> Optional[datetime]:
        value = row.get("update_time")
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day)
        text = str(value)
        for fmt, length in [("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)]:
            try:
                return datetime.strptime(text[:length], fmt)
            except ValueError:
                continue
        raise ValueError("update_time must be YYYY-MM-DD or YYYY-MM-DD HH:MM:SS")

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

    def _search_text(self, row: Dict[str, Any]) -> str:
        fields = [
            row.get("name"), row.get("college"), row.get("major"), row.get("position_name"),
            row.get("experiences"), row.get("project_experiences"), row.get("skills"),
        ]
        return json.dumps(fields, ensure_ascii=False, default=str).lower()

    def _follower_matches(self, row: Dict[str, Any], user_id: Any) -> bool:
        if row.get("follower_id") == user_id:
            return True
        follower_ids = row.get("follower_ids") or []
        if isinstance(follower_ids, str):
            follower_ids = [item.strip() for item in follower_ids.split(",") if item.strip()]
        elif not isinstance(follower_ids, (list, tuple, set)):
            follower_ids = [follower_ids]
        return str(user_id) in {str(follower_id).strip() for follower_id in follower_ids}
