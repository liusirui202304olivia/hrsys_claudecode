"""SQL dump 离线数据访问实现。

该文件解析内网导出的 SQL dump，提取核心招聘表并生成候选人、岗位、来源的联表视图。
它用于 P0 本地验证和测试，支持受控 filter、候选人详情读取和聚合分布计算。
该层会读取原始字段，但不会直接决定 Agent 可见字段；安全投影由服务层完成。
"""

import base64
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


ALLOWED_CANDIDATE_FILTERS = {
    "name_query",
    "position_query",
    "position_name",
    "position_id",
    "source_query",
    "source_id",
    "proposed_department_id",
    "hr_id",
    "candidate_status",
    "status",
    "min_work_years",
    "max_work_years",
    "gender",
    "degree",
    "college_query",
    "major_query",
    "is_focused",
    "manual_import",
    "match_point_min",
    "skills_any",
    "experience_keywords_any",
    "candidate_pool",
    "rejected_before_days",
    "status_updated_before",
    "status_updated_after",
    "proposed_join_date_from",
    "proposed_join_date_to",
    "create_time_from",
    "create_time_to",
    "update_time_from",
    "update_time_to",
}

VALID_CANDIDATE_POOLS = {"active", "old_rejected", "recent_rejected", "hired", "joining"}
DEFAULT_REJECTED_BEFORE_DAYS = 180
ALLOWED_DISTRIBUTIONS = {
    "position_name",
    "status",
    "source_name",
    "candidate_pool",
    "proposed_department_id",
    "hr_id",
    "degree",
    "college",
    "major",
    "gender",
    "work_years_band",
    "proposed_join_month",
    "create_month",
    "update_month",
}

INTERVIEW_SAFE_VIEW_COLUMNS = [
    "interview_id", "candidate_id", "candidate_name", "position_id", "position_name",
    "candidate_status", "interview_name", "interview_type", "interview_time",
    "interview_status", "create_time", "update_time",
]
INTERVIEW_EVALUATE_SAFE_VIEW_COLUMNS = [
    "evaluation_id", "interview_id", "candidate_id", "candidate_name", "position_id",
    "position_name", "candidate_status", "interviewer_id", "is_primary",
    "evaluate_data", "feedback", "evaluation_result", "question_data",
    "create_time", "update_time",
]
INTERVIEW_QUESTION_SAFE_VIEW_COLUMNS = [
    "evaluation_id", "interview_id", "candidate_id", "candidate_name", "position_id",
    "position_name", "candidate_status", "interviewer_id", "is_primary",
    "item_source", "question_index", "score", "question_title", "question_content",
    "question_answer", "question_feedback", "dimension", "evaluation_result",
    "create_time", "update_time",
]
SCREEN_EVALUATE_SAFE_VIEW_COLUMNS = [
    "screen_evaluate_id", "candidate_id", "candidate_name", "position_id",
    "position_name", "candidate_status", "screener_id", "feedback",
    "screen_result", "create_time", "update_time",
]


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

    def distribution(self, dimension: str, filters: Optional[Dict[str, Any]], identity_scope: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if dimension not in ALLOWED_DISTRIBUTIONS:
            raise ValueError("Unsupported distribution dimension: " + str(dimension))
        counts: Dict[str, int] = {}
        for row in self._aggregate_rows(filters or {}, identity_scope):
            key = self._distribution_value(row, dimension, filters or {})
            counts[key] = counts.get(key, 0) + 1
        return [
            {dimension: key, "count": count}
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))
        ]

    def execute_safe_sql(self, sql: str) -> List[Dict[str, Any]]:
        rows = self._joined_candidates()
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            connection.create_function("DATE_FORMAT", 2, self._sqlite_date_format)
            candidate_columns = sorted({key for row in rows for key in row.keys()})
            self._load_sqlite_view(connection, "v_candidate_agent_safe", rows, candidate_columns)
            self._load_sqlite_view(connection, "v_candidate_agent_privileged", rows, candidate_columns)
            self._load_sqlite_view(
                connection,
                "v_candidate_interview_safe",
                self._interview_safe_rows(),
                INTERVIEW_SAFE_VIEW_COLUMNS,
            )
            self._load_sqlite_view(
                connection,
                "v_candidate_interview_evaluate_safe",
                self._interview_evaluate_safe_rows(),
                INTERVIEW_EVALUATE_SAFE_VIEW_COLUMNS,
            )
            self._load_sqlite_view(
                connection,
                "v_candidate_interview_question_safe",
                self._interview_question_safe_rows(),
                INTERVIEW_QUESTION_SAFE_VIEW_COLUMNS,
            )
            self._load_sqlite_view(
                connection,
                "v_candidate_screen_evaluate_safe",
                self._screen_evaluate_safe_rows(),
                SCREEN_EVALUATE_SAFE_VIEW_COLUMNS,
            )
            cursor = connection.execute(sql)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()

    def _load_sqlite_view(
        self,
        connection: sqlite3.Connection,
        view_name: str,
        rows: List[Dict[str, Any]],
        columns: List[str],
    ) -> None:
        columns = list(columns or sorted({key for row in rows for key in row.keys()}))
        if not columns:
            columns = ["__empty__"]
        column_sql = ", ".join('"%s" TEXT' % column for column in columns)
        connection.execute('CREATE TABLE "%s" (%s)' % (view_name, column_sql))
        insert_sql = (
            'INSERT INTO "%s" (%s) VALUES (%s)' %
            (view_name, ", ".join('"%s"' % column for column in columns), ", ".join(["?"] * len(columns)))
        )
        for row in rows:
            values = [self._sqlite_value(row.get(column)) for column in columns]
            connection.execute(insert_sql, values)

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

    def _candidate_context_by_id(self) -> Dict[Any, Dict[str, Any]]:
        positions = {row.get("id"): row for row in self.table("hr_position")}
        result: Dict[Any, Dict[str, Any]] = {}
        for candidate in self.table("hr_candidate"):
            position = positions.get(candidate.get("position_id"), {})
            result[candidate.get("id")] = {
                "candidate_id": candidate.get("id"),
                "candidate_name": candidate.get("name"),
                "position_id": candidate.get("position_id"),
                "position_name": position.get("name"),
                "candidate_status": candidate.get("status"),
            }
        return result

    def _interview_safe_rows(self) -> List[Dict[str, Any]]:
        candidate_context = self._candidate_context_by_id()
        rows: List[Dict[str, Any]] = []
        for interview in self.table("hr_interview"):
            context = candidate_context.get(interview.get("candidate_id"), {})
            row = {
                "interview_id": interview.get("id"),
                "candidate_id": interview.get("candidate_id"),
                "candidate_name": context.get("candidate_name"),
                "position_id": context.get("position_id"),
                "position_name": context.get("position_name"),
                "candidate_status": context.get("candidate_status"),
                "interview_name": interview.get("name"),
                "interview_type": interview.get("interview_type"),
                "interview_time": interview.get("interview_time"),
                "interview_status": interview.get("status"),
                "create_time": interview.get("create_time"),
                "update_time": interview.get("update_time"),
            }
            rows.append(row)
        return rows

    def _interview_evaluate_safe_rows(self) -> List[Dict[str, Any]]:
        candidate_context = self._candidate_context_by_id()
        interviews = {row.get("id"): row for row in self.table("hr_interview")}
        rows: List[Dict[str, Any]] = []
        for evaluation in self.table("hr_interview_evaluate"):
            interview = interviews.get(evaluation.get("interview_id"), {})
            context = candidate_context.get(interview.get("candidate_id"), {})
            rows.append(self._interview_evaluate_base_row(evaluation, interview, context))
        return rows

    def _interview_question_safe_rows(self) -> List[Dict[str, Any]]:
        candidate_context = self._candidate_context_by_id()
        interviews = {row.get("id"): row for row in self.table("hr_interview")}
        rows: List[Dict[str, Any]] = []
        for evaluation in self.table("hr_interview_evaluate"):
            interview = interviews.get(evaluation.get("interview_id"), {})
            context = candidate_context.get(interview.get("candidate_id"), {})
            base = self._interview_evaluate_base_row(evaluation, interview, context)
            for item_source in ["evaluate_data", "question_data"]:
                for index, item in enumerate(self._json_array(evaluation.get(item_source)), start=1):
                    item_dict = item if isinstance(item, dict) else {"value": item}
                    rows.append({
                        "evaluation_id": base.get("evaluation_id"),
                        "interview_id": base.get("interview_id"),
                        "candidate_id": base.get("candidate_id"),
                        "candidate_name": base.get("candidate_name"),
                        "position_id": base.get("position_id"),
                        "position_name": base.get("position_name"),
                        "candidate_status": base.get("candidate_status"),
                        "interviewer_id": base.get("interviewer_id"),
                        "is_primary": base.get("is_primary"),
                        "item_source": item_source,
                        "question_index": index,
                        "score": self._numeric_value(item_dict.get("score")),
                        "question_title": item_dict.get("title") or item_dict.get("question_title") or item_dict.get("name"),
                        "question_content": item_dict.get("content") or item_dict.get("question_content") or item_dict.get("question"),
                        "question_answer": item_dict.get("answer") or item_dict.get("question_answer"),
                        "question_feedback": item_dict.get("feedback") or item_dict.get("question_feedback"),
                        "dimension": self._first_dimension(item_dict),
                        "evaluation_result": base.get("evaluation_result"),
                        "create_time": base.get("create_time"),
                        "update_time": base.get("update_time"),
                    })
        return rows

    def _screen_evaluate_safe_rows(self) -> List[Dict[str, Any]]:
        candidate_context = self._candidate_context_by_id()
        rows: List[Dict[str, Any]] = []
        for evaluation in self.table("hr_screen_evaluate"):
            context = candidate_context.get(evaluation.get("candidate_id"), {})
            rows.append({
                "screen_evaluate_id": evaluation.get("id"),
                "candidate_id": evaluation.get("candidate_id"),
                "candidate_name": context.get("candidate_name"),
                "position_id": context.get("position_id"),
                "position_name": context.get("position_name"),
                "candidate_status": context.get("candidate_status"),
                "screener_id": evaluation.get("screener_id"),
                "feedback": evaluation.get("feedback"),
                "screen_result": evaluation.get("result"),
                "create_time": evaluation.get("create_time"),
                "update_time": evaluation.get("update_time"),
            })
        return rows

    def _interview_evaluate_base_row(
        self,
        evaluation: Dict[str, Any],
        interview: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "evaluation_id": evaluation.get("id"),
            "interview_id": evaluation.get("interview_id"),
            "candidate_id": interview.get("candidate_id"),
            "candidate_name": context.get("candidate_name"),
            "position_id": context.get("position_id"),
            "position_name": context.get("position_name"),
            "candidate_status": context.get("candidate_status"),
            "interviewer_id": evaluation.get("interviewer_id"),
            "is_primary": evaluation.get("is_primary"),
            "evaluate_data": evaluation.get("evaluate_data"),
            "feedback": evaluation.get("feedback"),
            "evaluation_result": evaluation.get("result"),
            "question_data": evaluation.get("question_data"),
            "create_time": evaluation.get("create_time"),
            "update_time": evaluation.get("update_time"),
        }

    def _json_array(self, value: Any) -> List[Any]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except ValueError:
                return []
            return parsed if isinstance(parsed, list) else []
        return []

    def _numeric_value(self, value: Any) -> Optional[Union[int, float]]:
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return int(number) if number.is_integer() else number

    def _first_dimension(self, item: Dict[str, Any]) -> Optional[str]:
        if item.get("dimension") not in (None, ""):
            return str(item.get("dimension"))
        dimensions = item.get("dimensions")
        if isinstance(dimensions, list) and dimensions:
            return str(dimensions[0])
        if isinstance(dimensions, str) and dimensions:
            return dimensions
        return None

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
        if not self._date_range_matches(row, filters):
            return False
        if filters.get("name_query") and str(filters["name_query"]).lower() not in str(row.get("name") or "").lower():
            return False
        position_query = filters.get("position_query") or filters.get("position_name")
        if position_query:
            position_text = json.dumps(
                [row.get("position_name"), row.get("position_jd")],
                ensure_ascii=False,
                default=str,
            )
            if str(position_query).lower() not in position_text.lower():
                return False
        if filters.get("position_id") is not None and row.get("position_id") != filters.get("position_id"):
            return False
        if filters.get("source_id") is not None and row.get("source_id") != filters.get("source_id"):
            return False
        if filters.get("proposed_department_id") is not None and row.get("proposed_department_id") != filters.get("proposed_department_id"):
            return False
        if filters.get("hr_id") is not None and row.get("hr_id") != filters.get("hr_id"):
            return False
        if filters.get("source_query"):
            source_text = json.dumps([row.get("source_name"), row.get("source_full_name")], ensure_ascii=False, default=str).lower()
            if str(filters["source_query"]).lower() not in source_text:
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
        if filters.get("max_work_years") is not None:
            work_years = row.get("work_years")
            if work_years is None or int(work_years) > int(filters["max_work_years"]):
                return False
        for key in ["gender", "degree"]:
            if filters.get(key) is not None and row.get(key) != filters.get(key):
                return False
        for key, field_name in [("college_query", "college"), ("major_query", "major")]:
            if filters.get(key) and str(filters[key]).lower() not in str(row.get(field_name) or "").lower():
                return False
        for key in ["is_focused", "manual_import"]:
            if filters.get(key) is not None and bool(row.get(key)) != bool(filters.get(key)):
                return False
        if filters.get("match_point_min") is not None:
            match_point = row.get("match_point")
            if match_point is None or int(match_point) < int(filters["match_point_min"]):
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
            raise ValueError("candidate_pool must be one of active, old_rejected, recent_rejected, hired, joining")
        if candidate_pool is not None and (filters.get("status") is not None or filters.get("candidate_status") is not None):
            raise ValueError("candidate_pool cannot be combined with status or candidate_status")
        if "rejected_before_days" in filters:
            self._validate_positive_integer(filters.get("rejected_before_days"), "rejected_before_days")
        for key in [
            "status_updated_before", "status_updated_after",
            "proposed_join_date_from", "proposed_join_date_to",
            "create_time_from", "create_time_to",
            "update_time_from", "update_time_to",
        ]:
            if key in filters and filters.get(key) is not None:
                self._parse_yyyy_mm_dd(filters.get(key), key)

    def _candidate_pool_matches(self, row: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        candidate_pool = filters.get("candidate_pool")
        if not candidate_pool:
            return True
        status = row.get("status")
        if candidate_pool == "active":
            return status not in {"REJECTED", "HIRED"}
        if candidate_pool == "joining":
            return bool(row.get("proposed_join_date")) and status not in {"REJECTED", "HIRED"}
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

    def _date_range_matches(self, row: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        for prefix, field_name in [
            ("proposed_join_date", "proposed_join_date"),
            ("create_time", "create_time"),
            ("update_time", "update_time"),
        ]:
            start_key = prefix + "_from"
            end_key = prefix + "_to"
            if filters.get(start_key) is None and filters.get(end_key) is None:
                continue
            value = self._row_datetime(row, field_name)
            if filters.get(start_key) is not None:
                start = self._parse_yyyy_mm_dd(filters[start_key], start_key)
                if value is None or value < start:
                    return False
            if filters.get(end_key) is not None:
                end = self._parse_yyyy_mm_dd(filters[end_key], end_key).replace(hour=23, minute=59, second=59)
                if value is None or value > end:
                    return False
        return True

    def _rejected_cutoff(self, filters: Dict[str, Any]) -> datetime:
        days = filters.get("rejected_before_days", DEFAULT_REJECTED_BEFORE_DAYS)
        days = self._validate_positive_integer(days, "rejected_before_days")
        cutoff_date = date.today() - timedelta(days=days)
        return datetime(cutoff_date.year, cutoff_date.month, cutoff_date.day, 23, 59, 59)

    def _row_update_time(self, row: Dict[str, Any]) -> Optional[datetime]:
        return self._row_datetime(row, "update_time")

    def _row_datetime(self, row: Dict[str, Any], field_name: str) -> Optional[datetime]:
        value = row.get(field_name)
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
        raise ValueError(field_name + " must be YYYY-MM-DD or YYYY-MM-DD HH:MM:SS")

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
            row.get("position_jd"), row.get("experiences"), row.get("project_experiences"), row.get("skills"),
        ]
        return json.dumps(fields, ensure_ascii=False, default=str).lower()

    def _distribution_value(self, row: Dict[str, Any], dimension: str, filters: Dict[str, Any]) -> str:
        if dimension == "work_years_band":
            value = row.get("work_years")
            if value is None:
                return "UNKNOWN"
            years = int(value)
            if years <= 2:
                return "0-2"
            if years <= 5:
                return "3-5"
            if years <= 10:
                return "6-10"
            return "10+"
        if dimension == "proposed_join_month":
            return self._month_value(row.get("proposed_join_date"))
        if dimension == "create_month":
            return self._month_value(row.get("create_time"))
        if dimension == "update_month":
            return self._month_value(row.get("update_time"))
        if dimension == "candidate_pool":
            status = row.get("status")
            if status == "HIRED":
                return "hired"
            if status == "REJECTED":
                update_time = self._row_update_time(row)
                return "old_rejected" if update_time and update_time <= self._rejected_cutoff(filters) else "recent_rejected"
            if row.get("proposed_join_date"):
                return "joining"
            return "active"
        value = row.get(dimension)
        return str(value) if value not in (None, "") else "UNKNOWN"

    def _month_value(self, value: Any) -> str:
        if value in (None, ""):
            return "UNKNOWN"
        return str(value)[:7]

    def _sqlite_value(self, value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, (datetime, date)):
            return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
        return value

    def _sqlite_date_format(self, value: Any, fmt: str) -> Optional[str]:
        if value in (None, ""):
            return None
        text = str(value)
        if fmt == "%Y-%m":
            return text[:7]
        if fmt == "%Y":
            return text[:4]
        return text
