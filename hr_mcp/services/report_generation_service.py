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
