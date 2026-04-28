"""安全守护模块测试"""
import pytest
from src.guardian.detector import RiskDetector
from src.guardian.rules import SecurityRules
from src.agent.models import Intent, Environment, RiskLevel


@pytest.fixture
def detector():
    return RiskDetector()


@pytest.fixture
def rules():
    return SecurityRules()


@pytest.fixture
def env():
    return Environment(
        os_name="Linux",
        os_version="5.15.0",
        hostname="test-host",
        is_production=False,
        current_user="testuser",
    )


class TestSecurityRules:
    """安全规则测试"""

    def test_protected_path_detection(self, rules):
        """测试受保护路径检测"""
        assert rules.is_protected_path("/etc/passwd") is True
        assert rules.is_protected_path("/boot/vmlinuz") is True
        assert rules.is_protected_path("/tmp/test") is False
        assert rules.is_protected_path("/home/user/file") is False

    def test_high_risk_pattern_detection(self, rules):
        """测试高危模式检测"""
        assert rules.matches_high_risk_pattern("rm -rf /") is True
        assert rules.matches_high_risk_pattern("chmod 777") is True
        assert rules.matches_high_risk_pattern("ls -la") is False

    def test_confirmation_required(self, rules):
        """测试是否需要确认"""
        assert rules.requires_confirmation("delete", "file") is True
        assert rules.requires_confirmation("kill", "process") is True
        assert rules.requires_confirmation("create", "user") is True
        assert rules.requires_confirmation("list") is False


class TestRiskDetector:
    """风险检测器测试"""

    def test_low_risk_query(self, detector, env):
        """测试低风险查询操作"""
        intent = Intent(
            action="check_usage",
            target="",
            parameters={},
            raw_input="查看磁盘使用情况",
            capability_name="disk",
        )
        assessment = detector.assess(intent, env)
        assert assessment.level == RiskLevel.LOW
        assert assessment.needs_confirmation is False
        assert assessment.blocked is False

    def test_high_risk_protected_path(self, detector, env):
        """测试高风险受保护路径"""
        intent = Intent(
            action="delete",
            target="/etc/passwd",
            parameters={"path": "/etc/passwd"},
            raw_input="删除 /etc/passwd 文件",
            capability_name="file",
        )
        assessment = detector.assess(intent, env)
        assert assessment.level >= RiskLevel.HIGH
        assert assessment.needs_confirmation is True
        assert "保护路径" in assessment.reasons[0]

    def test_critical_risk_pattern(self, detector, env):
        """测试极高风险命令模式"""
        intent = Intent(
            action="delete",
            target="/",
            parameters={},
            raw_input="rm -rf /",
            capability_name="file",
        )
        assessment = detector.assess(intent, env)
        assert assessment.level == RiskLevel.CRITICAL
        assert assessment.blocked is True

    def test_user_management_high_risk(self, detector, env):
        """测试用户管理高风险操作"""
        intent = Intent(
            action="create",
            target="newuser",
            parameters={"username": "newuser"},
            raw_input="创建用户 newuser",
            capability_name="user",
        )
        assessment = detector.assess(intent, env)
        assert assessment.level >= RiskLevel.HIGH
        assert assessment.needs_confirmation is True

    def test_production_env_risk_escalation(self, detector):
        """测试生产环境风险升级"""
        prod_env = Environment(is_production=True)
        intent = Intent(
            action="delete",
            target="/tmp/test",
            parameters={"path": "/tmp/test"},
            raw_input="删除 /tmp/test",
            capability_name="file",
        )
        assessment = detector.assess(intent, prod_env)
        # 生产环境中删除操作风险会提升
        assert assessment.level >= RiskLevel.HIGH
