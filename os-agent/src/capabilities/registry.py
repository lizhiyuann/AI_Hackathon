"""能力注册中心 - 管理所有可用能力"""
from typing import Dict, List, Optional
from src.capabilities.base import BaseCapability
from src.utils.logger import log


class CapabilityRegistry:
    """能力注册中心 - 单例模式"""

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
        self._capabilities: Dict[str, BaseCapability] = {}
        self._auto_register()

    def _auto_register(self):
        """自动注册所有能力模块"""
        from src.capabilities.disk import DiskCapability
        from src.capabilities.file import FileCapability
        from src.capabilities.process import ProcessCapability
        from src.capabilities.user import UserCapability
        from src.capabilities.system import SystemCapability

        capabilities = [
            DiskCapability(),
            FileCapability(),
            ProcessCapability(),
            UserCapability(),
            SystemCapability(),
        ]

        for cap in capabilities:
            self.register(cap)

    def register(self, capability: BaseCapability):
        """注册能力"""
        self._capabilities[capability.name] = capability
        log.debug(f"注册能力: {capability.name} - {capability.description}")

    def find(self, action: str) -> Optional[BaseCapability]:
        """根据操作查找能力"""
        for cap in self._capabilities.values():
            if cap.supports(action):
                return cap
        return None

    def get(self, name: str) -> Optional[BaseCapability]:
        """根据名称获取能力"""
        return self._capabilities.get(name)

    def list_all(self) -> List[Dict]:
        """列出所有可用能力"""
        return [
            {
                "name": cap.name,
                "description": cap.description,
                "actions": cap.supported_actions,
            }
            for cap in self._capabilities.values()
        ]
