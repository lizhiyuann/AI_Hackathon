"""操作审计日志"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from src.agent.models import Intent, RiskAssessment, CapabilityResult, RiskLevel


# 审计日志目录
DATA_DIR = Path(__file__).parent.parent.parent / "data"
AUDIT_LOG_FILE = DATA_DIR / "audit.jsonl"


class AuditLogger:
    """操作审计日志记录器"""

    def __init__(self):
        DATA_DIR.mkdir(exist_ok=True)

    def log_operation(
        self,
        user_input: str,
        intent: Intent,
        risk_assessment: RiskAssessment,
        result: CapabilityResult,
    ):
        """记录操作审计日志"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "intent": {
                "action": intent.action,
                "target": intent.target,
                "parameters": intent.parameters,
                "capability": intent.capability_name,
            },
            "risk_assessment": {
                "level": risk_assessment.level.value,
                "reasons": risk_assessment.reasons,
                "blocked": risk_assessment.blocked,
            },
            "result": {
                "success": result.success,
                "commands": result.commands_executed,
                "error": result.error,
            },
        }

        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_recent_logs(self, limit: int = 20) -> list:
        """获取最近的审计日志"""
        if not AUDIT_LOG_FILE.exists():
            return []

        logs = []
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))

        return logs[-limit:]
