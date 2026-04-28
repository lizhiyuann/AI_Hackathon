"""意图解析模块测试"""
import pytest
import json
from unittest.mock import MagicMock
from src.understanding.intent import IntentParser


@pytest.fixture
def mock_llm():
    """创建 mock LLM"""
    llm = MagicMock()
    return llm


@pytest.fixture
def parser_with_llm(mock_llm):
    """创建带 mock LLM 的解析器"""
    return IntentParser(llm=mock_llm)


def _make_llm_response(mock_llm, capability, action, parameters=None, confidence=0.9):
    """让 mock LLM 返回指定的意图"""
    response = MagicMock()
    response.content = json.dumps({
        "capability": capability,
        "action": action,
        "parameters": parameters or {},
        "confidence": confidence,
    }, ensure_ascii=False)
    mock_llm.invoke.return_value = response


class TestIntentParser:
    """意图解析器测试"""

    def test_disk_usage_intent(self, parser_with_llm, mock_llm):
        """测试磁盘使用率查询意图"""
        _make_llm_response(mock_llm, "disk", "check_usage")
        intent = parser_with_llm.parse("查询磁盘使用情况")
        assert intent.capability_name == "disk"
        assert intent.action == "check_usage"
        assert intent.confidence > 0

    def test_disk_space_intent(self, parser_with_llm, mock_llm):
        """测试磁盘空间查询意图"""
        _make_llm_response(mock_llm, "disk", "check_usage")
        intent = parser_with_llm.parse("硬盘还有多少空间")
        assert intent.capability_name == "disk"

    def test_file_list_intent(self, parser_with_llm, mock_llm):
        """测试文件列表意图"""
        _make_llm_response(mock_llm, "file", "list")
        intent = parser_with_llm.parse("列出当前目录的文件")
        assert intent.capability_name == "file"
        assert intent.action == "list"

    def test_file_search_intent(self, parser_with_llm, mock_llm):
        """测试文件搜索意图"""
        _make_llm_response(mock_llm, "file", "search", {"name": "test.txt"})
        intent = parser_with_llm.parse("查找名为 test.txt 的文件")
        assert intent.capability_name == "file"
        assert intent.action == "search"

    def test_process_list_intent(self, parser_with_llm, mock_llm):
        """测试进程列表意图"""
        _make_llm_response(mock_llm, "process", "list")
        intent = parser_with_llm.parse("查看运行中的进程")
        assert intent.capability_name == "process"
        assert intent.action == "list"

    def test_port_check_intent(self, parser_with_llm, mock_llm):
        """测试端口查询意图"""
        _make_llm_response(mock_llm, "process", "check_port", {"port": "8080"})
        intent = parser_with_llm.parse("检查端口 8080 占用情况")
        assert intent.capability_name == "process"
        assert intent.action == "check_port"
        assert intent.parameters.get("port") == "8080"

    def test_user_list_intent(self, parser_with_llm, mock_llm):
        """测试用户列表意图"""
        _make_llm_response(mock_llm, "user", "list")
        intent = parser_with_llm.parse("查看系统用户")
        assert intent.capability_name == "user"
        assert intent.action == "list"

    def test_memory_info_intent(self, parser_with_llm, mock_llm):
        """测试内存信息意图"""
        _make_llm_response(mock_llm, "system", "memory")
        intent = parser_with_llm.parse("查看内存使用情况")
        assert intent.capability_name == "system"
        assert intent.action == "memory"

    def test_cpu_info_intent(self, parser_with_llm, mock_llm):
        """测试CPU信息意图"""
        _make_llm_response(mock_llm, "system", "cpu")
        intent = parser_with_llm.parse("查看CPU负载")
        assert intent.capability_name == "system"
        assert intent.action == "cpu"

    def test_network_info_intent(self, parser_with_llm, mock_llm):
        """测试网络信息意图"""
        _make_llm_response(mock_llm, "system", "network")
        intent = parser_with_llm.parse("查看网络配置")
        assert intent.capability_name == "system"
        assert intent.action == "network"

    def test_path_extraction(self, parser_with_llm, mock_llm):
        """测试路径提取"""
        _make_llm_response(mock_llm, "file", "list", {"path": "/home"})
        intent = parser_with_llm.parse("列出 /home 目录的文件")
        assert "path" in intent.parameters or "target" in intent.parameters

    def test_unknown_intent(self, parser_with_llm, mock_llm):
        """测试未知意图（LLM 返回闲聊）"""
        _make_llm_response(mock_llm, "chat", "greeting")
        intent = parser_with_llm.parse("今天天气怎么样")
        assert intent.capability_name == "chat"

    def test_env_hint_passed_to_llm(self, parser_with_llm, mock_llm):
        """测试环境提示被传递给 LLM"""
        _make_llm_response(mock_llm, "system", "network")
        parser_with_llm.parse("查看网络配置", env_hint="Linux/Ubuntu 24.04")
        # 验证 LLM 被调用
        mock_llm.invoke.assert_called_once()
        call_args = mock_llm.invoke.call_args[0][0]
        prompt_text = call_args[0].content
        assert "Ubuntu" in prompt_text

    def test_fallback_without_llm(self):
        """测试无 LLM 时的兜底解析"""
        parser = IntentParser(llm=None)
        intent = parser.parse("查看磁盘使用情况")
        assert intent.capability_name == "disk"
        assert intent.action == "check_usage"

    def test_fallback_unknown(self):
        """测试无 LLM 时未知意图返回闲聊"""
        parser = IntentParser(llm=None)
        intent = parser.parse("随便聊聊天")
        assert intent.capability_name == "chat"
        assert intent.action == "greeting"

    def test_parameter_regex_extraction(self, parser_with_llm, mock_llm):
        """测试参数的 regex 提取（端口号）"""
        _make_llm_response(mock_llm, "process", "check_port")
        intent = parser_with_llm.parse("检查端口 8080 占用情况")
        # regex 提取的端口参数应该存在
        assert intent.parameters.get("port") == "8080"

    def test_username_regex_extraction(self, parser_with_llm, mock_llm):
        """测试用户名的 regex 提取"""
        _make_llm_response(mock_llm, "user", "create", {"username": "testuser"})
        intent = parser_with_llm.parse("创建一个新用户testuser")
        assert intent.parameters.get("username") == "testuser"

    def test_new_password_regex_extraction(self, parser_with_llm, mock_llm):
        """测试新密码的 regex 提取"""
        _make_llm_response(mock_llm, "user", "modify", {"username": "testuser", "new_password": "abc123"})
        intent = parser_with_llm.parse("修改用户密码改成abc123")
        assert intent.parameters.get("new_password") == "abc123"

    def test_llm_returns_clarification(self, parser_with_llm, mock_llm):
        """测试 LLM 直接返回 needs_clarification=true"""
        response = MagicMock()
        response.content = json.dumps({
            "capability": "user",
            "action": "modify",
            "parameters": {},
            "confidence": 0.6,
            "needs_clarification": True,
            "clarification_question": "你是想修改哪个用户的密码？",
        }, ensure_ascii=False)
        mock_llm.invoke.return_value = response
        intent = parser_with_llm.parse("修改一下这个密码，改成abc123")
        assert intent.needs_clarification is True
        assert "哪个用户" in intent.clarification_question

    def test_llm_no_clarification_when_context_clear(self, parser_with_llm, mock_llm):
        """测试 LLM 从上下文能推断时不需要澄清"""
        _make_llm_response(mock_llm, "user", "modify", {"username": "test333", "new_password": "abc123"})
        context = "用户: 创建一个新用户test333\n助手: 用户 test333 已成功创建"
        intent = parser_with_llm.parse("修改一下这个密码，改成abc123", context=context)
        assert intent.needs_clarification is False

    def test_post_check_skip_readonly_action(self):
        """测试后置安全检查：只读操作不触发澄清"""
        from src.agent.models import Intent
        intent = Intent(
            action="list",
            capability_name="user",
            parameters={},
            raw_input="查看这个用户",
        )
        IntentParser._post_check_clarification(intent, "查看这个用户", "")
        assert intent.needs_clarification is False

    def test_post_check_skip_chat(self):
        """测试后置安全检查：闲聊不触发澄清"""
        from src.agent.models import Intent
        intent = Intent(
            action="greeting",
            capability_name="chat",
            parameters={},
            raw_input="这个怎么样",
        )
        IntentParser._post_check_clarification(intent, "这个怎么样", "")
        assert intent.needs_clarification is False

    def test_post_check_skip_non_destructive(self):
        """测试后置安全检查：create 不触发澄清"""
        from src.agent.models import Intent
        intent = Intent(
            action="create",
            capability_name="user",
            parameters={"username": "testuser"},
            raw_input="创建这个用户",
        )
        IntentParser._post_check_clarification(intent, "创建这个用户", "")
        assert intent.needs_clarification is False

    def test_post_check_trigger_destructive_no_context(self):
        """测试后置安全检查：破坏性操作 + 代词 + 无上下文 → 触发澄清"""
        from src.agent.models import Intent
        intent = Intent(
            action="modify",
            capability_name="user",
            parameters={"new_password": "abc123"},
            raw_input="修改一下这个密码，改成abc123",
        )
        IntentParser._post_check_clarification(intent, "修改一下这个密码，改成abc123", "")
        assert intent.needs_clarification is True
        assert len(intent.clarification_question) > 0

    def test_post_check_no_trigger_when_no_pronoun(self):
        """测试后置安全检查：无代词不触发澄清"""
        from src.agent.models import Intent
        intent = Intent(
            action="modify",
            capability_name="user",
            parameters={"username": "test333", "new_password": "abc123"},
            raw_input="修改用户test333的密码为abc123",
        )
        IntentParser._post_check_clarification(intent, "修改用户test333的密码为abc123", "")
        assert intent.needs_clarification is False

    def test_post_check_no_trigger_when_has_context(self):
        """测试后置安全检查：有上下文 + 代词 → 信任 LLM（不触发后置检查）"""
        from src.agent.models import Intent
        intent = Intent(
            action="modify",
            capability_name="user",
            parameters={"username": "test333", "new_password": "abc123"},
            raw_input="修改一下这个密码，改成abc123",
        )
        context = "用户: 创建一个新用户test333\n助手: 用户 test333 已成功创建"
        IntentParser._post_check_clarification(intent, "修改一下这个密码，改成abc123", context)
        assert intent.needs_clarification is False

    def test_post_check_trigger_delete_no_context(self):
        """测试后置安全检查：删除操作 + 代词 + 无上下文 → 触发澄清"""
        from src.agent.models import Intent
        intent = Intent(
            action="delete",
            capability_name="user",
            parameters={},
            raw_input="删掉那个用户",
        )
        IntentParser._post_check_clarification(intent, "删掉那个用户", "")
        assert intent.needs_clarification is True

    def test_json_extract_simple(self):
        """测试 JSON 提取"""
        text = '{"capability":"user","action":"list","confidence":0.9}'
        result = IntentParser._extract_json(text)
        assert result == text

    def test_json_extract_with_extra_text(self):
        """测试从多余文本中提取 JSON"""
        text = '这是我的回答：\n{"capability":"disk","action":"check_usage","confidence":0.9}\n其他内容'
        result = IntentParser._extract_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["capability"] == "disk"

    def test_json_extract_nested(self):
        """测试嵌套 JSON 提取"""
        text = '{"capability":"user","action":"create","parameters":{"username":"test"},"confidence":0.9}'
        result = IntentParser._extract_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["parameters"]["username"] == "test"

    def test_json_extract_no_json(self):
        """测试无 JSON 返回 None"""
        result = IntentParser._extract_json("这里没有 JSON")
        assert result is None

    def test_intent_default_clarification_fields(self, parser_with_llm, mock_llm):
        """测试 Intent 默认的澄清字段"""
        _make_llm_response(mock_llm, "disk", "check_usage")
        intent = parser_with_llm.parse("查看磁盘")
        assert intent.needs_clarification is False
        assert intent.clarification_question == ""
