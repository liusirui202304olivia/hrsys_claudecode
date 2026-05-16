"""招聘报告生成服务。

该文件把岗位标准、人才池分析和样本候选人组合成结构化 Markdown 报告。
报告包含概览、质量分析、样本候选人、风险点和下一步动作等部分。
它不直接访问数据库，输入应来自已经经过安全处理的 policy 与 analysis 结果。
"""

class ReportGenerationService:
    def generate_recruitment_report(self, report_type: str, policy: dict, analysis: dict, include_sections: list[str]) -> dict:
        position_name = policy.get("position_name") or policy.get("policy_id") or "岗位"
        title = f"{position_name}候选人池分析报告"
        sections = [f"# {title}", "", "## 概览", f"候选人总数：{analysis.get('summary_stats', {}).get('total_candidates', 0)}"]
        if "quality_analysis" in include_sections:
            sections.extend(["", "## 质量分析"])
            for observation in analysis.get("observations", []):
                sections.append(f"- {observation}")
        if "candidate_pool_overview" in include_sections:
            sections.extend(["", "## 样本候选人"])
            for candidate in analysis.get("sample_candidates", [])[:10]:
                sections.append(f"- {candidate.get('name', '未知')}：{candidate.get('status', 'UNKNOWN')}")
        if "risk_points" in include_sections:
            sections.extend(["", "## 风险", "- 需要面试验证候选人项目主导性和技术深度", "- 高权限联系方式不进入默认推荐上下文"])
        if "next_actions" in include_sections:
            sections.extend(["", "## 下一步", "- 对强匹配候选人安排技术面", "- 对证据不足项在面试中追问"])
        return {"title": title, "report_type": report_type, "content_markdown": "\n".join(sections)}
