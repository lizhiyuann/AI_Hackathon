"""能力基类 - 支持多发行版命令适配"""
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Any, Optional

from src.agent.models import RiskLevel, Environment, CapabilityResult
from src.utils.logger import log


# 能力配置文件路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "capabilities.json"


class BaseCapability(ABC):
    """能力基类 - 支持多平台多发行版命令适配"""

    name: str = ""
    description: str = ""
    supported_actions: List[str] = []
    risk_level: RiskLevel = RiskLevel.LOW

    def __init__(self):
        self._commands = {}
        self._load_config()

    def _load_config(self):
        """从配置文件加载命令定义"""
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cap_config = data.get("capabilities", {}).get(self.name, {})
                self._commands = cap_config.get("commands", {})
                if cap_config.get("description"):
                    self.description = cap_config["description"]
                log.debug(f"加载 {self.name} 能力配置，共 {len(self._commands)} 个命令")
            except Exception as e:
                log.error(f"加载能力配置失败: {e}")

    def supports(self, action: str) -> bool:
        """检查是否支持该操作"""
        return action in self.supported_actions

    def get_command(self, action: str, parameters: Dict[str, Any] = None, env: Environment = None) -> str:
        """获取命令模板并替换参数
        
        支持多平台 (Windows/Linux) 和多发行版命令适配
        
        Args:
            action: 操作名称
            parameters: 命令参数
            env: 环境信息，用于选择合适的命令变体
            
        Returns:
            格式化后的命令字符串
        """
        cmd_config = self._commands.get(action, {})
        if not cmd_config:
            log.warning(f"未找到 {self.name} 模块 {action} 操作的配置")
            return ""

        cmd_definition = cmd_config.get("cmd", "")
        
        # 情况1: 命令定义是字典 (多平台/多发行版)
        if isinstance(cmd_definition, dict):
            cmd_template = self._select_cmd_variant(cmd_definition, env)
        # 情况2: 命令定义是字符串 (通用命令)
        else:
            cmd_template = cmd_definition

        if not cmd_template:
            os_info = f"{env.os_name}/{env.distro_name}" if env else "未知环境"
            log.warning(f"未找到 {self.name} 模块 {action} 操作在 {os_info} 下的命令模板")
            return ""

        # 替换参数
        if parameters:
            for key, value in parameters.items():
                cmd_template = cmd_template.replace(f"{{{key}}}", str(value))

        return cmd_template

    def _select_cmd_variant(self, cmd_definition: Dict, env: Environment = None) -> str:
        """根据环境选择合适的命令变体
        
        Args:
            cmd_definition: 命令定义字典，可能包含:
                - windows: Windows命令
                - linux: 通用Linux命令
                - linux_variants: 特定Linux发行版命令 (可选)
            env: 环境信息
            
        Returns:
            选择的命令模板
        """
        if not env:
            # 没有环境信息，返回通用Linux命令作为默认
            return cmd_definition.get("linux", "")

        is_windows = env.os_name == "Windows"
        is_linux = env.os_name == "Linux"
        
        if is_windows:
            # 优先使用Windows特定命令
            return cmd_definition.get("windows", "")
        elif is_linux:
            # 尝试匹配具体的Linux发行版
            linux_variants = cmd_definition.get("linux_variants", {})
            
            # 如果有发行版信息，尝试精确匹配
            if env.distro_name and env.distro_name in linux_variants:
                log.debug(f"使用 {env.distro_name} 特定命令: {linux_variants[env.distro_name]}")
                return linux_variants[env.distro_name]
            
            # 回退到通用Linux命令
            return cmd_definition.get("linux", "")
        else:
            # 其他系统 (如macOS)，尝试使用通用Linux命令
            return cmd_definition.get("linux", "")

    def get_risk_level(self, action: str) -> RiskLevel:
        """获取操作风险等级"""
        cmd_config = self._commands.get(action, {})
        risk_str = cmd_config.get("risk", "low")
        try:
            return RiskLevel(risk_str)
        except ValueError:
            return RiskLevel.LOW

    def needs_confirmation(self, action: str) -> bool:
        """检查操作是否需要确认"""
        cmd_config = self._commands.get(action, {})
        return cmd_config.get("confirm", False)

    @abstractmethod
    def execute(self, action: str, parameters: Dict[str, Any], env: Environment, executor=None) -> CapabilityResult:
        """执行能力 - 子类必须实现
        
        Args:
            action: 操作名称
            parameters: 操作参数
            env: 执行环境信息
            executor: 命令执行器 (可选，默认使用LocalExecutor)
            
        Returns:
            CapabilityResult: 执行结果
        """
        pass
