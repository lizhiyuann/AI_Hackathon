"""代理核心模块测试"""
import pytest
import os
from src.agent.config import ConfigManager
from src.agent.memory import ConversationMemory
from src.agent.planner import TaskPlanner, TaskPlan
from src.agent.models import (
    Intent, Environment, RiskAssessment, RiskLevel,
    CapabilityResult, AgentResponse, ConversationTurn
)


class TestConfigManager:
    """配置管理器测试"""

    def test_singleton(self):
        """测试单例模式"""
        cm1 = ConfigManager()
        cm2 = ConfigManager()
        assert cm1 is cm2

    def test_app_config(self):
        """测试应用配置"""
        cm = ConfigManager()
        assert cm.app.name == "OS Agent"
        assert cm.app.version == "1.0.0"
        assert cm.app.language == "zh-CN"

    def test_agent_config(self):
        """测试代理配置"""
        cm = ConfigManager()
        assert cm.agent.max_conversation_turns == 50
        assert cm.agent.command_timeout == 30

    def test_llm_config(self):
        """测试LLM配置"""
        cm = ConfigManager()
        assert cm.llm.active_provider in ["deepseek", "tongyi", "zhipu", "moonshot", "openai"]
        assert len(cm.llm.providers) > 0

    def test_voice_config(self):
        """测试语音配置"""
        cm = ConfigManager()
        assert cm.voice.stt.engine in ["local", "api", "vosk", "whisper"]
        assert cm.voice.tts.engine in ["local", "api"]

    def test_get_active_llm_config(self):
        """测试获取激活的LLM配置"""
        cm = ConfigManager()
        config = cm.get_active_llm_config()
        assert config is not None


class TestConversationMemory:
    """对话记忆测试"""

    @pytest.fixture
    def memory(self, tmp_path):
        """创建临时记忆实例"""
        db_path = str(tmp_path / "test_memory.db")
        return ConversationMemory(db_path=db_path)

    def test_add_and_get_recent(self, memory):
        """测试添加和获取最近对话"""
        turn = ConversationTurn(
            timestamp="2026-04-23T12:00:00",
            user_input="测试输入",
            agent_response="测试响应",
            commands=["echo test"],
        )
        memory.add(turn)

        recent = memory.get_recent(1)
        assert len(recent) == 1
        assert recent[0].user_input == "测试输入"
        assert recent[0].agent_response == "测试响应"

    def test_get_context(self, memory):
        """测试获取上下文"""
        turn1 = ConversationTurn(user_input="问题1", agent_response="回答1")
        turn2 = ConversationTurn(user_input="问题2", agent_response="回答2")
        memory.add(turn1)
        memory.add(turn2)

        context = memory.get_context(window=2)
        assert "问题1" in context
        assert "回答1" in context
        assert "问题2" in context
        assert "回答2" in context

    def test_search(self, memory):
        """测试搜索对话"""
        turn = ConversationTurn(
            user_input="查找磁盘使用情况",
            agent_response="磁盘使用率45%",
        )
        memory.add(turn)

        results = memory.search("磁盘")
        assert len(results) == 1
        assert "磁盘" in results[0].user_input

    def test_clear(self, memory):
        """测试清空记忆"""
        turn = ConversationTurn(user_input="测试", agent_response="测试")
        memory.add(turn)

        memory.clear()
        recent = memory.get_recent(10)
        assert len(recent) == 0


class TestTaskPlanner:
    """任务规划器测试"""

    @pytest.fixture
    def planner(self):
        return TaskPlanner()

    def test_is_complex_task_simple(self, planner):
        """测试简单任务判断"""
        assert planner.is_complex_task("查看磁盘使用情况") is False

    def test_is_complex_task_complex(self, planner):
        """测试复杂任务判断"""
        assert planner.is_complex_task("查看磁盘然后删除临时文件") is True
        assert planner.is_complex_task("列出文件并且查看进程") is True

    def test_plan_simple(self, planner):
        """测试简单任务规划"""
        intents = [
            {"description": "查看磁盘", "command": "df -h", "capability": "disk", "parameters": {}}
        ]
        plan = planner.plan("查看磁盘使用情况", intents)

        assert isinstance(plan, TaskPlan)
        assert len(plan.steps) == 1
        assert plan.steps[0].description == "查看磁盘"
        assert plan.steps[0].status == "pending"

    def test_plan_complex(self, planner):
        """测试复杂任务规划"""
        intents = [
            {"description": "查看磁盘", "command": "df -h", "capability": "disk", "parameters": {}},
            {"description": "查看进程", "command": "ps aux", "capability": "process", "parameters": {}},
        ]
        plan = planner.plan("查看磁盘然后查看进程", intents)

        assert len(plan.steps) == 2
        assert plan.is_complex is True

    def test_task_plan_next_step(self):
        """测试获取下一步"""
        plan = TaskPlan(original_input="test")
        plan.steps = [
            type('TaskStep', (), {
                'step_id': 1, 'description': '步骤1', 'command': '',
                'capability_name': '', 'parameters': {}, 'depends_on': None,
                'status': 'completed'
            })(),
            type('TaskStep', (), {
                'step_id': 2, 'description': '步骤2', 'command': '',
                'capability_name': '', 'parameters': {}, 'depends_on': 1,
                'status': 'pending'
            })(),
        ]

        next_step = plan.get_next_step()
        assert next_step.step_id == 2

    def test_task_plan_is_complete(self):
        """测试任务完成判断"""
        plan = TaskPlan(original_input="test")
        plan.steps = [
            type('TaskStep', (), {
                'step_id': 1, 'description': '步骤1', 'command': '',
                'capability_name': '', 'parameters': {}, 'depends_on': None,
                'status': 'completed'
            })(),
            type('TaskStep', (), {
                'step_id': 2, 'description': '步骤2', 'command': '',
                'capability_name': '', 'parameters': {}, 'depends_on': 1,
                'status': 'completed'
            })(),
        ]

        assert plan.is_complete() is True


class TestModels:
    """数据模型测试"""

    def test_risk_level_comparison(self):
        """测试风险等级比较"""
        assert RiskLevel.LOW < RiskLevel.MEDIUM
        assert RiskLevel.MEDIUM < RiskLevel.HIGH
        assert RiskLevel.HIGH < RiskLevel.CRITICAL
        assert RiskLevel.LOW >= RiskLevel.LOW

    def test_intent_creation(self):
        """测试意图创建"""
        intent = Intent(
            action="check_usage",
            target="/",
            parameters={"path": "/home"},
            raw_input="查看磁盘使用情况",
            confidence=0.9,
            capability_name="disk",
        )
        assert intent.action == "check_usage"
        assert intent.target == "/"
        assert intent.confidence == 0.9

    def test_environment_creation(self):
        """测试环境信息创建"""
        env = Environment(
            os_name="Linux",
            os_version="5.15.0",
            hostname="test-host",
            current_user="testuser",
            is_production=False,
        )
        assert env.os_name == "Linux"
        assert env.is_production is False

    def test_risk_assessment_creation(self):
        """测试风险评估创建"""
        assessment = RiskAssessment(
            level=RiskLevel.HIGH,
            reasons=["涉及系统路径"],
            needs_confirmation=True,
            blocked=False,
        )
        assert assessment.level == RiskLevel.HIGH
        assert assessment.needs_confirmation is True

    def test_capability_result_creation(self):
        """测试能力执行结果创建"""
        result = CapabilityResult(
            success=True,
            output="执行成功",
            raw_output="原始输出",
            commands_executed=["df -h"],
            risk_level=RiskLevel.LOW,
        )
        assert result.success is True
        assert len(result.commands_executed) == 1

    def test_agent_response_creation(self):
        """测试代理响应创建"""
        response = AgentResponse(
            success=True,
            message="操作完成",
            commands_executed=["ls -la"],
            risk_level=RiskLevel.LOW,
        )
        assert response.success is True
        assert response.message == "操作完成"
