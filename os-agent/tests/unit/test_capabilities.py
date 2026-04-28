"""能力模块测试 - 兼容Windows和Linux环境"""
import sys
import pytest
import os
import shutil
from src.capabilities.registry import CapabilityRegistry
from src.capabilities.disk import DiskCapability
from src.capabilities.file import FileCapability
from src.capabilities.system import SystemCapability
from src.connector.local import LocalExecutor
from src.connector.probe import EnvironmentProbe
from src.agent.models import Environment


IS_WINDOWS = sys.platform == "win32"


@pytest.fixture
def registry():
    return CapabilityRegistry()


@pytest.fixture
def executor():
    return LocalExecutor(timeout=10)


@pytest.fixture
def env():
    """创建真实的环境信息"""
    probe = EnvironmentProbe()
    return probe.detect()


class TestCapabilityRegistry:
    """能力注册中心测试"""

    def test_registry_has_all_capabilities(self, registry):
        """测试注册中心包含所有能力"""
        all_caps = registry.list_all()
        cap_names = [cap["name"] for cap in all_caps]
        assert "disk" in cap_names
        assert "file" in cap_names
        assert "process" in cap_names
        assert "user" in cap_names
        assert "system" in cap_names

    def test_find_capability_by_action(self, registry):
        """测试根据操作查找能力"""
        cap = registry.find("check_usage")
        assert cap is not None
        assert cap.name == "disk"

    def test_find_unknown_action(self, registry):
        """测试查找未知操作"""
        cap = registry.find("unknown_action")
        assert cap is None

    def test_get_capability_by_name(self, registry):
        """测试根据名称获取能力"""
        cap = registry.get("disk")
        assert cap is not None
        assert isinstance(cap, DiskCapability)


class TestDiskCapability:
    """磁盘管理能力测试"""

    def test_check_disk_usage(self, registry, env):
        """测试查看磁盘使用率"""
        disk = registry.get("disk")
        result = disk.execute("check_usage", {}, env)
        assert result.success is True
        assert "文件系统" in result.output or "/" in result.output
        assert len(result.commands_executed) > 0


class TestFileCapability:
    """文件操作能力测试"""

    def test_list_directory(self, registry, env):
        """测试列出目录内容"""
        file_cap = registry.get("file")
        path = "C:\\Users" if IS_WINDOWS else "/tmp"
        result = file_cap.execute("list", {"path": path}, env)
        assert "目录" in result.output

    def test_search_file(self, registry, env):
        """测试搜索文件"""
        file_cap = registry.get("file")
        result = file_cap.execute("search", {"path": ".", "pattern": "*.py"}, env)
        # 搜索结果可能为空，但应该返回结果
        assert result is not None

    def test_create_dir(self, registry, env):
        """测试创建目录"""
        file_cap = registry.get("file")
        test_path = "os_agent_test_dir_tmp"
        result = file_cap.execute("create_dir", {"path": test_path}, env)
        assert result.success is True
        # 清理
        if os.path.exists(test_path):
            shutil.rmtree(test_path)


class TestSystemCapability:
    """系统信息能力测试"""

    def test_system_info(self, registry, env):
        """测试查看系统信息"""
        sys_cap = registry.get("system")
        result = sys_cap.execute("info", {}, env)
        assert result.success is True
        assert "Linux" in result.output or "Windows" in result.output

    def test_memory_info(self, registry, env):
        """测试查看内存信息"""
        sys_cap = registry.get("system")
        result = sys_cap.execute("memory", {}, env)
        assert result.success is True
        assert "Mem:" in result.output or "内存" in result.output

    def test_cpu_info(self, registry, env):
        """测试查看CPU信息"""
        sys_cap = registry.get("system")
        result = sys_cap.execute("cpu", {}, env)
        assert "CPU" in result.output
