"""连接器模块测试"""
import sys
import pytest
from src.connector.local import LocalExecutor
from src.connector.probe import EnvironmentProbe


IS_WINDOWS = sys.platform == "win32"


@pytest.fixture
def executor():
    return LocalExecutor(timeout=5)


@pytest.fixture
def probe():
    return EnvironmentProbe()


class TestLocalExecutor:
    """本地执行器测试"""

    def test_execute_simple_command(self, executor):
        """测试执行简单命令"""
        cmd = "echo hello" if IS_WINDOWS else "echo 'hello'"
        result = executor.execute(cmd)
        assert result.success is True
        assert "hello" in result.output
        assert result.return_code == 0

    def test_execute_failed_command(self, executor):
        """测试执行失败命令"""
        result = executor.execute("nonexistent_command_12345")
        assert result.success is False

    def test_execute_with_timeout(self, executor):
        """测试命令执行"""
        cmd = "echo test" if IS_WINDOWS else "echo 'test'"
        result = executor.execute(cmd, timeout=5)
        assert result.success is True


class TestEnvironmentProbe:
    """环境探测测试"""

    def test_detect_environment(self, probe):
        """测试环境探测"""
        env = probe.detect()
        assert env.os_name != ""
        assert env.hostname != ""
        assert env.current_user != ""
        assert env.working_dir != ""

    def test_detect_os_info(self, probe):
        """测试操作系统信息探测"""
        env = probe.detect()
        assert env.os_name in ["Linux", "Windows", "Darwin"]
