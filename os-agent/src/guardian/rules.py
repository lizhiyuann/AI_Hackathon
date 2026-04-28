"""安全规则引擎"""
import json
from pathlib import Path
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "guardian.json"


class SecurityRules:
    """安全规则引擎"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._load_config()

    def _load_config(self):
        """加载安全配置"""
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.protected_paths: List[str] = data.get("protected_paths", [])
            self.high_risk_patterns: List[str] = data.get("high_risk_patterns", [])
            self.confirmation_actions: List[str] = data.get("confirmation_actions", [])
            self.blocked_commands: List[str] = data.get("blocked_commands", [])
            self.max_command_length: int = data.get("max_command_length", 1000)
            self.risk_levels_config: Dict[str, Any] = data.get("risk_levels", {})
            self.environment_rules: Dict[str, Any] = data.get("environment_risk_multipliers", {})
            self.max_batch_operations: int = data.get("max_batch_operations", 10)
            self.max_search_results: int = data.get("max_search_results", 50)
        else:
            self.protected_paths = []
            self.high_risk_patterns = []
            self.confirmation_actions = []
            self.blocked_commands = []
            self.max_command_length = 1000
            self.risk_levels_config = {}
            self.environment_rules = {}
            self.max_batch_operations = 10
            self.max_search_results = 50

    def is_protected_path(self, path: str) -> bool:
        """检查路径是否为受保护路径"""
        path = path.rstrip("/")
        for protected in self.protected_paths:
            if path == protected or path.startswith(protected + "/"):
                return True
        return False

    def matches_high_risk_pattern(self, command: str) -> bool:
        """检查命令是否匹配高危模式"""
        for pattern in self.high_risk_patterns:
            if pattern in command:
                return True
        return False

    def requires_confirmation(self, action: str, capability_name: str = "") -> bool:
        """检查操作是否需要确认

        支持两种格式：
        - 带前缀： "file.delete", "user.create" （guardian.json 配置格式）
        - 纯 action："delete", "create" （代码传入格式）
        """
        # 先尝试带前缀的匹配
        if capability_name:
            full_action = f"{capability_name}.{action}"
            if full_action in self.confirmation_actions:
                return True
        # 再尝试纯 action 匹配
        return action in self.confirmation_actions

    def check_batch_limit(self, command: str) -> bool:
        """检查命令是否可能触发批量操作限制

        Returns:
            True if the command exceeds batch limits and should be blocked.
        """
        import re
        # 检查 rm 命令中是否使用了通配符（批量删除）
        rm_patterns = [
            r'rm\s+.*\*',
            r'rm\s+-[a-zA-Z]*r.*\*',
            r'find\s+/\s+.*-delete',
            r'find\s+/\s+.*-exec\s+rm',
        ]
        for pattern in rm_patterns:
            if re.search(pattern, command):
                return True
        return False

    def is_blocked_command(self, command: str) -> bool:
        """检查命令是否在黑名单中"""
        for blocked in self.blocked_commands:
            if blocked in command:
                return True
        return False

    def check_command_length(self, command: str) -> bool:
        """检查命令是否超过最大长度限制"""
        return len(command) > self.max_command_length

    def get_batch_limit(self) -> int:
        """获取批量操作上限"""
        return self.max_batch_operations

    def get_search_limit(self) -> int:
        """获取搜索结果上限"""
        return self.max_search_results
