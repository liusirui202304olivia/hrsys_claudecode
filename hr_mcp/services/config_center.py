from __future__ import annotations

import os
from pathlib import Path


class ConfigCenter:
    def __init__(self, project_root: str | Path | None = None, env_path: str | Path | None = None):
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.env_path = Path(env_path) if env_path else self.project_root / ".env"
        self.env = dict(os.environ)
        self.env.update(self._read_env_file(self.env_path))

    @classmethod
    def for_tests(cls, project_root: str | Path):
        return cls(project_root=project_root)

    @property
    def audit_path(self) -> Path:
        return self.project_root / "runtime" / "audit" / "audit.jsonl"

    @property
    def result_path(self) -> Path:
        return self.project_root / "runtime" / "results" / "screening_results.jsonl"

    @property
    def dump_path(self) -> Path:
        return self.project_root / "hr_data_sample" / "devops_hr_user_data_0508_1.sql"

    @property
    def policy_dir(self) -> Path:
        return self.project_root / "config" / "policies"

    @property
    def standard_markdown_dir(self) -> Path:
        return self.project_root / "standard_markdown"

    @property
    def host(self) -> str:
        return self.env.get("HR_MCP_HOST", "127.0.0.1")

    @property
    def port(self) -> int:
        return int(self.env.get("HR_MCP_PORT", "8765"))

    @property
    def data_backend(self) -> str:
        return self.env.get("HR_DATA_BACKEND", "dump").lower()

    @property
    def mysql_config(self) -> dict:
        return {
            "host": self.env.get("HR_DB_HOST", "127.0.0.1"),
            "port": int(self.env.get("HR_DB_PORT", "3306")),
            "user": self.env.get("HR_DB_USER", ""),
            "password": self.env.get("HR_DB_PASSWORD", ""),
            "database": self.env.get("HR_DB_NAME", "devops"),
        }

    def get_bool(self, key: str, default: bool = False) -> bool:
        raw = self.env.get(key)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def get_int(self, key: str, default: int | None = None) -> int | None:
        raw = self.env.get(key)
        if raw is None or raw == "":
            return default
        return int(raw)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.env.get(key, default)

    def _read_env_file(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values
