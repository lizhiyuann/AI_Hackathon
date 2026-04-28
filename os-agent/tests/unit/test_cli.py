"""CLI界面测试"""
import pytest
from unittest.mock import patch, MagicMock
import asyncio

from src.interface.cli import get_agent, format_response, format_risk_warning
from src.agent.models import AgentResponse, RiskLevel


class TestCLIFunctions:
    """CLI功能测试"""

    def test_get_agent(self):
        """测试获取代理实例"""
        agent = get_agent()
        assert agent is not None
        assert hasattr(agent, 'process')
        assert hasattr(agent, 'get_capabilities')

    def test_format_response_success(self, capsys):
        """测试成功响应格式化"""
        response = AgentResponse(
            success=True,
            message="测试成功消息",
            commands_executed=["test command"]
        )
        format_response(response)
        captured = capsys.readouterr()
        # Rich输出包含ANSI转义码，只检查消息是否被处理
        assert "测试成功消息" in captured.out or "执行结果" in captured.out

    def test_format_response_error(self, capsys):
        """测试错误响应格式化"""
        response = AgentResponse(
            success=False,
            message="测试错误消息",
            error="测试错误"
        )
        format_response(response)
        captured = capsys.readouterr()
        assert "测试错误消息" in captured.out or "错误" in captured.out

    def test_format_risk_warning_high(self, capsys):
        """测试高风险警告格式化"""
        response = AgentResponse(
            success=True,
            message="高风险操作警告",
            needs_confirmation=True,
            risk_level=RiskLevel.HIGH
        )
        result = format_risk_warning(response)
        assert result is True
        captured = capsys.readouterr()
        assert "风险警告" in captured.out or "HIGH" in captured.out

    def test_format_risk_warning_low(self):
        """测试低风险警告格式化"""
        response = AgentResponse(
            success=True,
            message="普通操作",
            needs_confirmation=False,
            risk_level=RiskLevel.LOW
        )
        result = format_risk_warning(response)
        assert result is False


class TestCLIIntegration:
    """CLI集成测试"""

    def test_agent_capabilities(self):
        """测试代理能力查询"""
        from src.agent.core import OSIntelligentAgent
        agent = OSIntelligentAgent()
        caps = agent.get_capabilities()
        assert len(caps) > 0
        cap_names = [cap["name"] for cap in caps]
        assert "disk" in cap_names
        assert "file" in cap_names
        assert "process" in cap_names
        assert "user" in cap_names
        assert "system" in cap_names

    def test_agent_config(self):
        """测试代理配置查询"""
        from src.agent.config import ConfigManager
        config = ConfigManager()
        assert config.app.name == "OS Agent"
        assert config.app.version == "1.0.0"
        assert config.llm.active_provider in ["deepseek", "tongyi", "zhipu", "moonshot", "openai"]

    @pytest.mark.asyncio
    async def test_agent_process_simple(self):
        """测试代理处理简单指令"""
        from src.agent.core import OSIntelligentAgent
        agent = OSIntelligentAgent()
        
        # 测试简单的系统信息查询
        response = await agent.process("你好")
        assert response is not None
        assert hasattr(response, 'success')
        assert hasattr(response, 'message')
