"""字段权限策略定义。

该文件维护 HR MCP 可向 Agent 暴露的默认字段、高权限字段和拒绝字段规则。
它强制高权限字段必须由高权限角色并携带访问理由才能返回，未列入白名单的字段默认拒绝。
候选人姓名、性别和拟入职时间按需求原文开放，联系方式则被限制在高权限路径。
字段策略默认来自代码内置常量，也可从项目内 `config/field_policy.yml` 加载，避免配置文件和运行时策略漂移。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union


class FieldAccessError(ValueError):
    pass


DEFAULT_VISIBLE_FIELDS: Dict[str, Set[str]] = {
    "hr_candidate": {
        "candidate_id", "status", "reject_stage", "hr_id", "name", "gender", "degree_first",
        "degree", "degree_start", "degree_end", "college", "major", "work_years",
        "experiences", "latest_interview_id", "proposed_join_date",
        "proposed_department_id", "is_focused", "match_point", "create_time",
        "update_time", "manual_import", "project_experiences", "skills",
        "position_id", "position_name", "position_category", "position_jd",
        "position_is_active", "source_id", "source_name", "source_full_name",
    },
    "hr_position": {"name", "category", "jd", "is_active"},
    "hr_screen_evaluate": {"id", "candidate_id", "screener_id", "feedback", "result", "create_time", "update_time"},
    "hr_interview": {"id", "candidate_id", "name", "interview_type", "interview_time", "status", "create_time", "update_time"},
    "hr_candidate_follower": {"id", "candidate_id", "follower_id", "is_current"},
    "sys_user": {
        "id", "name", "belong_org_id", "gender", "employee_type", "leader_id",
        "job", "site", "hire_date", "probation_months", "conversion_date",
        "last_day", "status",
    },
    "sys_org": {"name", "leader_id", "member_count"},
}

PRIVILEGED_VISIBLE_FIELDS: Dict[str, Set[str]] = {
    "hr_candidate": {"mobile", "email"},
    "sys_user": {"phone", "email", "username"},
}

PRIVILEGED_ROLES = {"HR_ADMIN"}


@dataclass
class FieldPolicy:
    default_fields: Dict[str, Set[str]] = field(default_factory=lambda: {k: set(v) for k, v in DEFAULT_VISIBLE_FIELDS.items()})
    privileged_fields: Dict[str, Set[str]] = field(default_factory=lambda: {k: set(v) for k, v in PRIVILEGED_VISIBLE_FIELDS.items()})
    privileged_roles: Set[str] = field(default_factory=lambda: set(PRIVILEGED_ROLES))

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "FieldPolicy":
        path = Path(path)
        if not path.exists():
            return cls()
        parsed = _parse_field_policy_yaml(path.read_text(encoding="utf-8"))
        return cls(
            default_fields={key: set(value) for key, value in parsed.get("default_visible", {}).items()},
            privileged_fields={key: set(value) for key, value in parsed.get("privileged_visible", {}).items()},
            privileged_roles=set(parsed.get("privileged_roles", [])),
        )

    def allowed_fields(self, table: str, requested_fields: Optional[Union[List[str], Tuple[str, ...]]], role: str, access_reason: Optional[str]) -> List[str]:
        fields = list(requested_fields or sorted(self.default_fields.get(table, set())))
        allowed_default = self.default_fields.get(table, set())
        allowed_privileged = self.privileged_fields.get(table, set())
        result: List[str] = []
        denied: List[str] = []
        for field_name in fields:
            if field_name in allowed_default:
                result.append(field_name)
            elif field_name in allowed_privileged:
                if role not in self.privileged_roles:
                    raise FieldAccessError(f"Field {table}.{field_name} requires privileged role")
                if not access_reason:
                    raise FieldAccessError(f"Field {table}.{field_name} requires X-Access-Reason")
                result.append(field_name)
            else:
                denied.append(field_name)
        if denied:
            raise FieldAccessError(f"Fields are not visible to agent: {table}.{', '.join(denied)}")
        return result

    def default_field_list(self, table: str) -> List[str]:
        return sorted(self.default_fields.get(table, set()))

    def has_privileged_fields(self, table: str, fields: Optional[Union[List[str], Tuple[str, ...]]]) -> bool:
        if not fields:
            return False
        privileged = self.privileged_fields.get(table, set())
        return any(field_name in privileged for field_name in fields)


def _parse_field_policy_yaml(text: str) -> Dict[str, object]:
    result: Dict[str, object] = {
        "default_visible": {},
        "privileged_visible": {},
        "privileged_roles": [],
    }
    section: Optional[str] = None
    current_table: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("\ufeff"):
            line = line.lstrip("\ufeff")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0 and stripped.endswith(":"):
            section = stripped[:-1]
            current_table = None
            continue
        if indent == 0 and ":" in stripped:
            key, raw_value = stripped.split(":", 1)
            if key == "privileged_roles":
                result["privileged_roles"] = _parse_inline_list(raw_value)
            continue
        if section in {"default_visible", "privileged_visible"} and indent == 2 and ":" in stripped:
            table_name, raw_value = stripped.split(":", 1)
            current_table = table_name.strip()
            section_map = result[section]
            assert isinstance(section_map, dict)
            section_map[current_table] = _parse_inline_list(raw_value) if raw_value.strip() else []
            continue
        if section in {"default_visible", "privileged_visible"} and indent >= 4 and stripped.startswith("- ") and current_table:
            section_map = result[section]
            assert isinstance(section_map, dict)
            section_map[current_table].append(stripped[2:].strip())
    return result


def _parse_inline_list(raw_value: str) -> List[str]:
    value = raw_value.strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",")]
    return [value.strip('"').strip("'")]
