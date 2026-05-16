from hr_mcp.http.app import serve
from hr_mcp.services.config_center import ConfigCenter


def main() -> None:
    serve(ConfigCenter())


if __name__ == "__main__":
    main()
