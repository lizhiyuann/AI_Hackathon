"""数据模型定义"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def __ge__(self, other):
        if self.__class__ is other.__class__:
            order = [self.LOW, self.MEDIUM, self.HIGH, self.CRITICAL]
            return order.index(self) >= order.index(other)
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            order = [self.LOW, self.MEDIUM, self.HIGH, self.CRITICAL]
            return order.index(self) > order.index(other)
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            order = [self.LOW, self.MEDIUM, self.HIGH, self.CRITICAL]
            return order.index(self) <= order.index(other)
        return NotImplemented

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            order = [self.LOW, self.MEDIUM, self.HIGH, self.CRITICAL]
            return order.index(self) < order.index(other)
        return NotImplemented


@dataclass
class Intent:
    """用户意图"""
    action: str                          # 操作类型
    target: str = ""                     # 操作目标
    parameters: Dict[str, Any] = field(default_factory=dict)
    raw_input: str = ""                  # 原始输入
    confidence: float = 0.0              # 置信度
    capability_name: str = ""            # 匹配的能力名称
    needs_clarification: bool = False    # 是否需要向用户澄清
    clarification_question: str = ""     # 澄清问题


@dataclass
class Environment:
    """服务器环境信息"""
    os_name: str = ""           # Windows/Linux
    os_version: str = ""
    distro_name: str = ""       # 发行版: CentOS, Ubuntu, openEuler, Debian, Fedora等
    distro_version: str = ""    # 发行版版本
    hostname: str = ""
    kernel: str = ""
    is_production: bool = False
    current_user: str = ""
    working_dir: str = ""
    package_manager: str = ""   # yum/apt/dnf


@dataclass
class RiskAssessment:
    """风险评估结果"""
    level: RiskLevel = RiskLevel.LOW
    reasons: List[str] = field(default_factory=list)
    needs_confirmation: bool = False
    blocked: bool = False


@dataclass
class CapabilityResult:
    """能力执行结果"""
    success: bool = True
    output: str = ""
    raw_output: str = ""
    commands_executed: List[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    error: Optional[str] = None
    verification_command: Optional[str] = None
    verification_expect_success: bool = True


@dataclass
class AgentResponse:
    """代理响应"""
    success: bool = True
    message: str = ""
    commands_executed: List[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    needs_confirmation: bool = False
    confirmation_prompt: str = ""
    error: Optional[str] = None
    progress: Optional[str] = None


@dataclass
class ConversationTurn:
    """对话轮次"""
    timestamp: str = ""
    user_input: str = ""
    agent_response: str = ""
    intent: Optional[Intent] = None
    commands: List[str] = field(default_factory=list)
