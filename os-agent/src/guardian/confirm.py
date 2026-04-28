"""二次确认机制"""
from src.agent.models import RiskAssessment


class ConfirmationManager:
    """二次确认管理器"""

    def create_confirmation_prompt(self, assessment: RiskAssessment) -> str:
        """创建确认提示"""
        risk_level = assessment.level.value.upper()
        reasons_text = "\n".join(f"  - {r}" for r in assessment.reasons)

        prompt = f"""
警告：该操作被识别为 {risk_level} 风险等级

风险原因:
{reasons_text}

请确认是否继续执行此操作？
输入 'yes' 或 'y' 确认，输入其他任意内容取消。
"""
        return prompt.strip()
