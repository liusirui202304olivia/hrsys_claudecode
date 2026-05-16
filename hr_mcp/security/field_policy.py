from dataclasses import dataclass, field


class FieldAccessError(ValueError):
    pass


DEFAULT_VISIBLE_FIELDS: dict[str, set[str]] = {
    "hr_candidate": {
        "status", "reject_stage", "hr_id", "name", "gender", "degree_first",
        "degree", "degree_start", "degree_end", "college", "major", "work_years",
        "experiences", "latest_interview_id", "proposed_join_date",
        "proposed_department_id", "is_focused", "match_point", "create_time",
        "update_time", "manual_import", "project_experiences", "skills",
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

PRIVILEGED_VISIBLE_FIELDS: dict[str, set[str]] = {
    "hr_candidate": {"mobile", "email"},
    "sys_user": {"phone", "email", "username"},
}

PRIVILEGED_ROLES = {"HR_ADMIN"}


@dataclass
class FieldPolicy:
    default_fields: dict[str, set[str]] = field(default_factory=lambda: {k: set(v) for k, v in DEFAULT_VISIBLE_FIELDS.items()})
    privileged_fields: dict[str, set[str]] = field(default_factory=lambda: {k: set(v) for k, v in PRIVILEGED_VISIBLE_FIELDS.items()})
    privileged_roles: set[str] = field(default_factory=lambda: set(PRIVILEGED_ROLES))

    def allowed_fields(self, table: str, requested_fields: list[str] | tuple[str, ...] | None, role: str, access_reason: str | None) -> list[str]:
        fields = list(requested_fields or sorted(self.default_fields.get(table, set())))
        allowed_default = self.default_fields.get(table, set())
        allowed_privileged = self.privileged_fields.get(table, set())
        result: list[str] = []
        denied: list[str] = []
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

    def default_field_list(self, table: str) -> list[str]:
        return sorted(self.default_fields.get(table, set()))
