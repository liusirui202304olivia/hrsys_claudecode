from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


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


class DumpTalentRepository:
    def __init__(self, dump_path: str | Path):
        self.dump_path = Path(dump_path)
        self._columns: dict[str, list[str]] | None = None
        self._tables: dict[str, list[dict[str, Any]]] | None = None

    def ready(self) -> bool:
        return self.dump_path.exists()

    def table(self, table_name: str) -> list[dict[str, Any]]:
        self._ensure_loaded()
        assert self._tables is not None
        return self._tables.get(table_name, [])

    def search_candidates(self, filters: dict[str, Any] | None, limit: int) -> list[dict[str, Any]]:
        filters = filters or {}
        self._validate_filters(filters)
        rows = [row for row in self._joined_candidates() if self._candidate_matches(row, filters)]
        return rows[: max(0, min(int(limit), 10_000))]

    def get_candidates_by_ids(self, candidate_ids: list[int | str]) -> list[dict[str, Any]]:
        ids = {str(candidate_id) for candidate_id in candidate_ids}
        return [row for row in self._joined_candidates() if str(row.get("id")) in ids or str(row.get("candidate_id")) in ids]

    def count_candidates(self, filters: dict[str, Any] | None) -> int:
        return len(self.search_candidates(filters or {}, 10_000_000))

    def position_distribution(self, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for row in self.search_candidates(filters or {}, 10_000_000):
            key = row.get("position_name") or "UNKNOWN"
            counts[key] = counts.get(key, 0) + 1
        return [
            {"position_name": key, "count": count}
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def status_distribution(self, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for row in self.search_candidates(filters or {}, 10_000_000):
            key = row.get("status") or "UNKNOWN"
            counts[key] = counts.get(key, 0) + 1
        return [
            {"status": key, "count": count}
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def source_distribution(self, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for row in self.search_candidates(filters or {}, 10_000_000):
            key = row.get("source_name") or "UNKNOWN"
            counts[key] = counts.get(key, 0) + 1
        return [
            {"source_name": key, "count": count}
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def _validate_filters(self, filters: dict[str, Any]) -> None:
        unknown = sorted(set(filters) - ALLOWED_CANDIDATE_FILTERS)
        if unknown:
            raise ValueError(f"Unsupported candidate filters: {', '.join(unknown)}")

    def _ensure_loaded(self) -> None:
        if self._tables is not None:
            return
        text = self.dump_path.read_text(encoding="utf-8", errors="replace")
        self._columns = self._parse_columns(text)
        self._tables = {}
        for table_name, columns in self._columns.items():
            rows = self._iter_insert_rows(text, table_name)
            self._tables[table_name] = [dict(zip(columns, row)) for row in rows]

    def _parse_columns(self, text: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for match in re.finditer(r"CREATE TABLE `([^`]+)` \((.*?)\) ENGINE=", text, re.S):
            table_name = match.group(1)
            columns: list[str] = []
            for line in match.group(2).splitlines():
                stripped = line.strip()
                if stripped.startswith("`"):
                    columns.append(stripped.split("`", 2)[1])
            result[table_name] = columns
        return result

    def _iter_insert_rows(self, text: str, table_name: str) -> list[list[Any]]:
        rows: list[list[Any]] = []
        pattern = re.compile(r"INSERT INTO `" + re.escape(table_name) + r"` VALUES")
        for match in pattern.finditer(text):
            i = match.end()
            depth = 0
            in_string = False
            escaped = False
            field = ""
            row: list[str] = []
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

    def _joined_candidates(self) -> list[dict[str, Any]]:
        positions = {row.get("id"): row for row in self.table("hr_position")}
        sources = {row.get("id"): row for row in self.table("hr_source")}
        joined: list[dict[str, Any]] = []
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
            joined.append(row)
        return joined

    def _candidate_matches(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
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

    def _search_text(self, row: dict[str, Any]) -> str:
        fields = [
            row.get("name"), row.get("college"), row.get("major"), row.get("position_name"),
            row.get("experiences"), row.get("project_experiences"), row.get("skills"),
        ]
        return json.dumps(fields, ensure_ascii=False, default=str).lower()
