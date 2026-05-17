"""配置中心服务。

该文件统一加载 `.env`、环境变量和项目路径配置，包括 HTTP 监听地址、数据后端、MySQL 连接、
审计路径、Bearer token 配置、IP 白名单、限流和请求体大小限制。
它只暴露配置读取能力，不保存业务状态，也不把数据库密钥写入 Claude Code CLI 配置。
内网 HTTP-MCP 中心服务通过这些配置完成自建鉴权和安全边界，不再依赖 API Gateway 注入身份。
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


class ConfigCenter:
    def __init__(self, project_root=None, env_path=None):
        # type: (Optional[Union[str, Path]], Optional[Union[str, Path]]) -> None
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.env_path = Path(env_path) if env_path else self.project_root / ".env"
        self.env = dict(os.environ)
        self.env.update(self._read_env_file(self.env_path))

    @classmethod
    def for_tests(cls, project_root):
        # type: (Union[str, Path]) -> "ConfigCenter"
        return cls(project_root=project_root)

    @property
    def audit_path(self):
        # type: () -> Path
        return self.project_root / "runtime" / "audit" / "audit.jsonl"

    @property
    def result_path(self):
        # type: () -> Path
        return self.project_root / "runtime" / "results" / "screening_results.jsonl"

    @property
    def dump_path(self):
        # type: () -> Path
        return self.project_root / "hr_data_sample" / "devops_hr_user_data_0508_1.sql"

    @property
    def policy_dir(self):
        # type: () -> Path
        return self.project_root / "config" / "policies"

    @property
    def field_policy_path(self):
        # type: () -> Path
        return self.project_root / "config" / "field_policy.yml"

    @property
    def auth_tokens_path(self):
        # type: () -> Path
        raw = self.env.get("HR_AUTH_TOKENS_PATH", "config/auth_tokens.json")
        path = Path(raw)
        return path if path.is_absolute() else self.project_root / path

    @property
    def standard_markdown_dir(self):
        # type: () -> Path
        return self.project_root / "standard_markdown"

    @property
    def host(self):
        # type: () -> str
        return self.env.get("HR_MCP_HOST", "127.0.0.1")

    @property
    def port(self):
        # type: () -> int
        return int(self.env.get("HR_MCP_PORT", "8765"))

    @property
    def data_backend(self):
        # type: () -> str
        raw = self.env.get("HR_DATA_BACKEND")
        if raw is None or not raw.strip():
            raise ValueError("HR_DATA_BACKEND must be explicitly configured as mysql or dump")
        value = raw.strip().lower()
        if value not in {"mysql", "dump"}:
            raise ValueError("Unsupported HR_DATA_BACKEND: " + raw)
        return value

    @property
    def allowed_ip_cidrs(self):
        # type: () -> List[str]
        raw = self.env.get("HR_ALLOWED_IP_CIDRS", "")
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def rate_limit_per_minute(self):
        # type: () -> int
        return int(self.env.get("HR_RATE_LIMIT_PER_MINUTE", "0") or "0")

    @property
    def max_request_bytes(self):
        # type: () -> int
        return int(self.env.get("HR_MAX_REQUEST_BYTES", "1048576") or "1048576")

    @property
    def mysql_config(self):
        # type: () -> Dict[str, object]
        return {
            "host": self.env.get("HR_DB_HOST", "127.0.0.1"),
            "port": int(self.env.get("HR_DB_PORT", "3306")),
            "user": self.env.get("HR_DB_USER", ""),
            "password": self.env.get("HR_DB_PASSWORD", ""),
            "database": self.env.get("HR_DB_NAME", "devops"),
        }

    def get_bool(self, key, default=False):
        # type: (str, bool) -> bool
        raw = self.env.get(key)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def get_int(self, key, default=None):
        # type: (str, Optional[int]) -> Optional[int]
        raw = self.env.get(key)
        if raw is None or raw == "":
            return default
        return int(raw)

    def get(self, key, default=None):
        # type: (str, Optional[str]) -> Optional[str]
        return self.env.get(key, default)

    def _read_env_file(self, path):
        # type: (Path) -> Dict[str, str]
        if not path.exists():
            return {}
        values = {}  # type: Dict[str, str]
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values
