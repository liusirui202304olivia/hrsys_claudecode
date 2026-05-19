"""安全 SQL 沙箱策略。

该文件定义 Agent 自写 SQL 的最小可执行边界：只允许单条 SELECT、只允许访问候选人安全视图、
只允许使用字段权限策略确认过的字段，并强制明细返回行数上限。
它不连接数据库，也不做 HR 业务判断；调用方必须先通过本策略校验，再把 SQL 交给 repository 执行。
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from hr_mcp.models.context import IdentityContext
from hr_mcp.security.field_policy import FieldAccessError, FieldPolicy

try:
    import sqlparse  # type: ignore
except ImportError:  # pragma: no cover - local tests may run without optional dependency
    sqlparse = None


class SafeSqlValidationError(ValueError):
    pass


@dataclass
class SafeSqlPlan:
    sql: str
    view_name: str
    limit: int
    fields: List[str]
    privileged: bool = False


class SafeSqlPolicy:
    SAFE_VIEW = "v_candidate_agent_safe"
    PRIVILEGED_VIEW = "v_candidate_agent_privileged"
    INTERVIEW_VIEW = "v_candidate_interview_safe"
    INTERVIEW_EVALUATE_VIEW = "v_candidate_interview_evaluate_safe"
    INTERVIEW_QUESTION_VIEW = "v_candidate_interview_question_safe"
    SCREEN_EVALUATE_VIEW = "v_candidate_screen_evaluate_safe"
    DEFAULT_VIEW_FIELD_POLICY_KEY = {
        SAFE_VIEW: "hr_candidate",
        PRIVILEGED_VIEW: "hr_candidate",
        INTERVIEW_VIEW: INTERVIEW_VIEW,
        INTERVIEW_EVALUATE_VIEW: INTERVIEW_EVALUATE_VIEW,
        INTERVIEW_QUESTION_VIEW: INTERVIEW_QUESTION_VIEW,
        SCREEN_EVALUATE_VIEW: SCREEN_EVALUATE_VIEW,
    }
    VIEW_DESCRIPTIONS = {
        SAFE_VIEW: "Default candidate safe profile view. It excludes contact fields.",
        PRIVILEGED_VIEW: "Privileged candidate safe profile view for contact fields.",
        INTERVIEW_VIEW: "Interview records with candidate and position context. It excludes operational links and platform IDs.",
        INTERVIEW_EVALUATE_VIEW: "Interview evaluation text, result, and JSON payloads with candidate and position context.",
        INTERVIEW_QUESTION_VIEW: "Normalized interview evaluation items expanded from evaluation JSON for score, question, answer, feedback, and dimension analysis.",
        SCREEN_EVALUATE_VIEW: "Screening evaluation text and result with candidate and position context.",
    }
    VIEW_RECOMMENDED_USE = {
        SAFE_VIEW: "Use for candidate profile lookup, candidate pool facts, status/date filtering, and open-ended candidate facts.",
        PRIVILEGED_VIEW: "Use only when an HR_ADMIN has an access reason to retrieve candidate contact fields.",
        INTERVIEW_VIEW: "Use for interview timelines, interview statuses, interview type counts, and candidate interview history.",
        INTERVIEW_EVALUATE_VIEW: "Use for interview feedback, evaluation results, raw evaluation JSON, and candidate evaluation context.",
        INTERVIEW_QUESTION_VIEW: "Use for AVG(score), score distributions, question/answer review, dimension analysis, and interviewer score comparisons.",
        SCREEN_EVALUATE_VIEW: "Use for initial screening feedback, screening pass/reject results, and screening result aggregation.",
    }
    VIEW_AGGREGATABLE_FIELDS = {
        SAFE_VIEW: {
            "status", "position_id", "position_name", "source_id", "source_name",
            "proposed_department_id", "hr_id", "degree", "college", "major",
            "gender", "work_years", "proposed_join_date", "create_time", "update_time",
        },
        PRIVILEGED_VIEW: {
            "status", "position_id", "position_name", "source_id", "source_name",
            "proposed_department_id", "hr_id", "degree", "college", "major",
            "gender", "work_years", "proposed_join_date", "create_time", "update_time",
        },
        INTERVIEW_VIEW: {
            "candidate_id", "position_id", "position_name", "candidate_status",
            "interview_type", "interview_status", "interview_time", "create_time", "update_time",
        },
        INTERVIEW_EVALUATE_VIEW: {
            "candidate_id", "position_id", "position_name", "candidate_status",
            "interviewer_id", "is_primary", "evaluation_result", "create_time", "update_time",
        },
        INTERVIEW_QUESTION_VIEW: {
            "candidate_id", "position_id", "position_name", "candidate_status",
            "interviewer_id", "is_primary", "item_source", "score", "dimension",
            "evaluation_result", "create_time", "update_time",
        },
        SCREEN_EVALUATE_VIEW: {
            "candidate_id", "position_id", "position_name", "candidate_status",
            "screener_id", "screen_result", "create_time", "update_time",
        },
    }
    MAX_ROWS = 300
    DEFAULT_ROWS = 300

    FORBIDDEN_KEYWORDS = {
        "insert", "update", "delete", "drop", "create", "alter", "truncate", "replace",
        "grant", "revoke", "call", "execute", "load", "outfile", "infile", "handler",
        "lock", "unlock", "set", "use",
    }
    FORBIDDEN_FUNCTIONS = {"sleep", "benchmark", "load_file", "sys_eval", "sys_exec"}
    ALLOWED_FUNCTIONS = {
        "count", "sum", "avg", "min", "max", "date", "date_format", "year", "month",
        "day", "coalesce", "ifnull", "nullif", "cast", "concat", "lower", "upper",
        "substring", "substr", "round",
    }
    SQL_KEYWORDS = {
        "select", "from", "where", "and", "or", "not", "in", "is", "null", "like",
        "between", "group", "by", "order", "asc", "desc", "limit", "offset", "as",
        "distinct", "case", "when", "then", "else", "end", "on", "true", "false",
        "having",
    }

    def __init__(self, field_policy: FieldPolicy):
        self.field_policy = field_policy

    def validate(self, sql: str, identity: IdentityContext) -> SafeSqlPlan:
        if not isinstance(sql, str) or not sql.strip():
            raise SafeSqlValidationError("sql must be a non-empty string")
        normalized = self._normalize_sql(sql)
        stripped_literals = self._strip_string_literals(normalized)
        lowered = stripped_literals.lower()
        self._reject_comments(stripped_literals)
        self._reject_forbidden_tokens(lowered)
        if not re.match(r"^\s*select\b", lowered):
            raise SafeSqlValidationError("Only SELECT statements are allowed")
        if re.search(r"\bjoin\b", lowered):
            raise SafeSqlValidationError("JOIN is not allowed in safe SQL; query the denormalized safe view")
        view_name, table_alias = self._extract_single_view(stripped_literals)
        privileged = view_name == self.PRIVILEGED_VIEW
        allowed_fields = self._allowed_fields_for_view(view_name, identity)
        selected_fields = self._validate_identifiers(stripped_literals, view_name, table_alias, allowed_fields)
        self._enforce_readonly_scope(stripped_literals, view_name, selected_fields, identity)
        limited_sql, limit = self._apply_limit(normalized)
        return SafeSqlPlan(
            sql=limited_sql,
            view_name=view_name,
            limit=limit,
            fields=sorted(selected_fields),
            privileged=privileged,
        )

    def _normalize_sql(self, sql: str) -> str:
        if sqlparse is not None:
            parsed = [statement for statement in sqlparse.parse(sql) if str(statement).strip().strip(";")]
            if len(parsed) != 1:
                raise SafeSqlValidationError("Only one SQL statement is allowed")
        normalized = sql.strip()
        if normalized.endswith(";"):
            normalized = normalized[:-1].strip()
        if ";" in normalized:
            raise SafeSqlValidationError("Only one SQL statement is allowed")
        return " ".join(normalized.split())

    def _strip_string_literals(self, sql: str) -> str:
        result = []
        in_string = False
        quote = ""
        escaped = False
        for char in sql:
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    in_string = False
                result.append(" ")
            else:
                if char in ("'", '"'):
                    in_string = True
                    quote = char
                    result.append(" ")
                else:
                    result.append(char)
        if in_string:
            raise SafeSqlValidationError("Unterminated string literal")
        return "".join(result)

    def _reject_comments(self, sql_without_literals: str) -> None:
        if "--" in sql_without_literals or "/*" in sql_without_literals or "*/" in sql_without_literals or "#" in sql_without_literals:
            raise SafeSqlValidationError("SQL comments are not allowed")

    def _reject_forbidden_tokens(self, lowered_sql: str) -> None:
        for keyword in self.FORBIDDEN_KEYWORDS:
            if re.search(r"\b" + re.escape(keyword) + r"\b", lowered_sql):
                raise SafeSqlValidationError("Unsafe SQL keyword is not allowed: " + keyword)
        for function in self.FORBIDDEN_FUNCTIONS:
            if re.search(r"\b" + re.escape(function) + r"\s*\(", lowered_sql):
                raise SafeSqlValidationError("Unsafe SQL function is not allowed: " + function)

    def _extract_single_view(self, sql_without_literals: str) -> Tuple[str, Optional[str]]:
        matches = list(re.finditer(
            r"\bfrom\s+`?([A-Za-z_][A-Za-z0-9_]*)`?(?:\s+(?:as\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
            sql_without_literals,
            flags=re.IGNORECASE,
        ))
        if len(matches) != 1:
            raise SafeSqlValidationError("Safe SQL must query exactly one safe view")
        view_name = matches[0].group(1)
        alias = matches[0].group(2)
        if view_name not in self.DEFAULT_VIEW_FIELD_POLICY_KEY:
            raise SafeSqlValidationError("Safe SQL can only query approved HR safe views")
        if alias and alias.lower() in self.SQL_KEYWORDS:
            alias = None
        return view_name, alias

    def _allowed_fields_for_view(self, view_name: str, identity: IdentityContext) -> Set[str]:
        field_policy_key = self.DEFAULT_VIEW_FIELD_POLICY_KEY.get(view_name)
        default_fields = set(self.field_policy.default_fields.get(field_policy_key or "", set()))
        if view_name not in {self.SAFE_VIEW, self.PRIVILEGED_VIEW}:
            return default_fields
        if view_name == self.SAFE_VIEW:
            return default_fields
        if identity.role not in self.field_policy.privileged_roles:
            raise FieldAccessError("Privileged safe SQL requires HR_ADMIN role")
        if not identity.access_reason:
            raise FieldAccessError("Privileged safe SQL requires access_reason")
        return default_fields.union(set(self.field_policy.privileged_fields.get("hr_candidate", set())))

    def _validate_identifiers(
        self,
        sql_without_literals: str,
        view_name: str,
        table_alias: Optional[str],
        allowed_fields: Set[str],
    ) -> Set[str]:
        aliases = set(self._select_aliases(sql_without_literals))
        if table_alias:
            aliases.add(table_alias)
        allowed_names = set(allowed_fields).union(aliases).union({view_name})
        allowed_names = allowed_names.union(self.SQL_KEYWORDS).union(self.ALLOWED_FUNCTIONS)
        referenced_fields = set()
        for prefix, field_name in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b", sql_without_literals):
            if prefix not in aliases and prefix != view_name:
                raise SafeSqlValidationError("Unknown table alias in safe SQL: " + prefix)
            if field_name not in allowed_fields:
                raise FieldAccessError("Field " + view_name + "." + field_name + " is not visible to this role")
            referenced_fields.add(field_name)
        for identifier in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", sql_without_literals):
            lowered = identifier.lower()
            if lowered in allowed_names or identifier in allowed_names:
                if identifier in allowed_fields:
                    referenced_fields.add(identifier)
                continue
            raise SafeSqlValidationError("Unknown or unsafe identifier in SQL: " + identifier)
        return referenced_fields

    def _enforce_readonly_scope(
        self,
        sql_without_literals: str,
        view_name: str,
        selected_fields: Set[str],
        identity: IdentityContext,
    ) -> None:
        if identity.role != "READONLY_VIEWER":
            return
        lowered = sql_without_literals.lower()
        has_aggregate = any(
            re.search(r"\b" + re.escape(function_name) + r"\s*\(", lowered)
            for function_name in ["count", "sum", "avg", "min", "max"]
        )
        if not has_aggregate:
            raise FieldAccessError("READONLY_VIEWER can only run aggregate safe SQL")
        aggregatable_fields = self.VIEW_AGGREGATABLE_FIELDS.get(view_name, set())
        detail_fields = sorted(set(selected_fields) - set(aggregatable_fields))
        if detail_fields:
            raise FieldAccessError(
                "READONLY_VIEWER aggregate safe SQL can only reference aggregatable fields: " +
                ", ".join(detail_fields)
            )

    def _select_aliases(self, sql_without_literals: str) -> List[str]:
        aliases = []
        for alias in re.findall(r"\bas\s+([A-Za-z_][A-Za-z0-9_]*)\b", sql_without_literals, flags=re.IGNORECASE):
            aliases.append(alias)
        return aliases

    def _apply_limit(self, sql: str) -> Tuple[str, int]:
        limit_match = re.search(r"\blimit\s+([0-9]+)\s*$", sql, flags=re.IGNORECASE)
        if not limit_match:
            return sql + " LIMIT " + str(self.DEFAULT_ROWS), self.DEFAULT_ROWS
        limit_value = int(limit_match.group(1))
        if limit_value < 1 or limit_value > self.MAX_ROWS:
            raise SafeSqlValidationError("Safe SQL LIMIT must be between 1 and " + str(self.MAX_ROWS))
        return sql, limit_value

    def describe_schema(self, identity: IdentityContext) -> Dict[str, Any]:
        views: Dict[str, Dict[str, Any]] = {}
        for view_name, field_policy_key in self.DEFAULT_VIEW_FIELD_POLICY_KEY.items():
            fields = sorted(self.field_policy.default_fields.get(field_policy_key, set()))
            view_schema: Dict[str, Any] = {
                "description": self.VIEW_DESCRIPTIONS[view_name],
                "recommended_use": self.VIEW_RECOMMENDED_USE[view_name],
                "fields": fields,
                "privileged_fields": [],
                "aggregatable_fields": sorted(self.VIEW_AGGREGATABLE_FIELDS.get(view_name, set())),
            }
            if view_name == self.PRIVILEGED_VIEW:
                view_schema.update({
                    "privileged_fields": sorted(self.field_policy.privileged_fields.get("hr_candidate", set())),
                    "requires_role": "HR_ADMIN",
                    "requires_access_reason": True,
                    "available_to_current_identity": bool(identity.role in self.field_policy.privileged_roles and identity.access_reason),
                })
            views[view_name] = view_schema
        return {
            "max_rows": self.MAX_ROWS,
            "rules": [
                "Only one SELECT statement is allowed.",
                "Only one approved safe view may be queried.",
                "JOIN is not allowed in Agent-authored safe SQL.",
                "Raw HR tables and fields outside this schema are rejected.",
                "LIMIT is required by policy and capped at 300 rows.",
            ],
            "views": views,
        }
