"""飞书适配器占位实现。

该文件为 P1/P2 的飞书机器人、消息推送或审批联动预留边界。
P0 阶段 HR MCP 主链路不调用该适配器，因此这里不包含招聘筛选、字段权限或数据访问逻辑。
后续扩展飞书能力时，应继续通过 tool/service 层调用受控能力，不能直连数据库。
"""

class FeishuAdapter:
    """P1/P2 placeholder. P0 SQL recruiting assistant does not call Feishu APIs."""

    def is_enabled(self) -> bool:
        return False
