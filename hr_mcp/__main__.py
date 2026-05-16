"""命令行启动入口。

该文件支持通过 `python -m hr_mcp` 启动本地 HTTP MCP 服务。
它只负责创建默认配置并调用 HTTP server，不解析业务请求、不访问数据库，也不注册具体工具逻辑。
实际依赖装配在 runtime/service 层完成，HTTP 请求处理在 `hr_mcp.http.app` 中完成。
"""

from hr_mcp.http.app import serve
from hr_mcp.services.config_center import ConfigCenter


def main() -> None:
    serve(ConfigCenter())


if __name__ == "__main__":
    main()
