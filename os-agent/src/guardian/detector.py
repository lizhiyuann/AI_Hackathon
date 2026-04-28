"""风险检测器"""
from typing import Optional

from src.agent.models import Intent, Environment, RiskAssessment, RiskLevel
from src.guardian.rules import SecurityRules
from src.utils.logger import log


class RiskDetector:
    """风险检测器"""

    def __init__(self):
        self.rules = SecurityRules()

    def assess(self, intent: Intent, env: Environment) -> RiskAssessment:
        """评估操作风险等级"""
        reasons = []
        risk = RiskLevel.LOW

        # 检查目标路径
        target_path = intent.target or intent.parameters.get("path", "")
        if target_path and self.rules.is_protected_path(target_path):
            risk = max(risk, RiskLevel.HIGH)
            reasons.append(f"目标路径 '{target_path}' 是系统保护路径")

        # 检查操作类型
        high_risk_actions = ["delete", "format", "mkfs", "kill_force", "modify"]
        if intent.action in high_risk_actions:
            risk = max(risk, RiskLevel.HIGH)
            reasons.append(f"操作类型 '{intent.action}' 是高风险操作")

        # 检查用户管理操作
        if intent.capability_name == "user" and intent.action in ["create", "delete", "modify"]:
            risk = max(risk, RiskLevel.HIGH)
            reasons.append(f"用户管理操作 '{intent.action}' 需要确认")

        # 检查是否匹配高危命令模式
        if self.rules.matches_high_risk_pattern(intent.raw_input):
            risk = RiskLevel.CRITICAL
            reasons.append("命令匹配高危模式")

        # 环境感知：如果是生产环境，提高风险等级
        if env.is_production and risk >= RiskLevel.MEDIUM:
            if risk == RiskLevel.MEDIUM:
                risk = RiskLevel.HIGH
                reasons.append("当前为生产环境，风险等级提升")

        needs_confirmation = risk >= RiskLevel.HIGH
        blocked = risk == RiskLevel.CRITICAL

        return RiskAssessment(
            level=risk,
            reasons=reasons,
            needs_confirmation=needs_confirmation,
            blocked=blocked,
        )
