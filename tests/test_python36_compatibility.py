"""Python 3.6 兼容性扫描测试。

该文件用静态扫描保护 `hr_mcp/` 运行代码不再使用 Python 3.6.8 无法解析的语法。
内网中心化 HTTP-MCP 服务固定运行在 Python 3.6.8，因此这些检查比普通风格检查更关键。
"""

import re
from pathlib import Path


FORBIDDEN_PATTERNS = [
    ("future_annotations", re.compile(r"from __future__ import annotations")),
    ("pep604_union", re.compile(r"\b[A-Za-z_][A-Za-z0-9_\.]*\s*\|\s*[A-Za-z_][A-Za-z0-9_\.]*")),
    ("builtin_generic_dict", re.compile(r"\bdict\s*\[")),
    ("builtin_generic_list", re.compile(r"\blist\s*\[")),
    ("builtin_generic_tuple", re.compile(r"\btuple\s*\[")),
    ("builtin_generic_set", re.compile(r"\bset\s*\[")),
    ("threading_http_server", re.compile(r"\bThreadingHTTPServer\b")),
]


def test_hr_mcp_runtime_code_uses_python36_compatible_syntax():
    root = Path(__file__).resolve().parents[1] / "hr_mcp"
    violations = []

    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for name, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                violations.append("%s:%s" % (path.relative_to(root.parent), name))

    assert violations == []
