"""上下文管理模块测试"""
import pytest
from src.understanding.context import ContextManager
from src.agent.models import ConversationTurn


@pytest.fixture
def ctx():
    return ContextManager()


class TestExtractEntities:
    """实体提取测试"""

    def test_extract_new_user_no_space(self, ctx):
        """测试提取'新用户xxx'模式（无空格）"""
        context = "用户: 创建一个新用户test333\n助手: 用户 test333 已成功创建"
        entities = ctx._extract_entities_from_context(context)
        assert "test333" in entities

    def test_extract_user_with_space(self, ctx):
        """测试提取'用户 xxx'模式（有空格）"""
        context = "用户: 查看用户 testuser 的权限\n助手: testuser 是普通用户"
        entities = ctx._extract_entities_from_context(context)
        assert "testuser" in entities

    def test_extract_user_no_space(self, ctx):
        """测试提取'用户xxx'模式（无空格）"""
        context = "用户: 用户admin123有什么权限\n助手: admin123 拥有管理员权限"
        entities = ctx._extract_entities_from_context(context)
        assert "admin123" in entities

    def test_extract_paths(self, ctx):
        """测试提取路径"""
        context = "用户: 查看 /home/test 目录\n助手: 目录内容..."
        entities = ctx._extract_entities_from_context(context)
        assert any("/home/test" in e for e in entities)

    def test_extract_multiple_users(self, ctx):
        """测试提取多个用户名"""
        context = (
            "用户: 创建一个新用户alice\n"
            "助手: alice 已创建\n"
            "用户: 创建一个新用户bob\n"
            "助手: bob 已创建"
        )
        entities = ctx._extract_entities_from_context(context)
        assert "alice" in entities
        assert "bob" in entities

    def test_extract_dedup(self, ctx):
        """测试去重"""
        context = "用户: 创建一个新用户testuser\n助手: OK\n用户: 用户 testuser 的权限\n助手: OK"
        entities = ctx._extract_entities_from_context(context)
        assert entities.count("testuser") == 1

    def test_extract_empty_context(self, ctx):
        """测试空上下文"""
        assert ctx._extract_entities_from_context("") == []

    def test_chinese_char_not_matched_as_username(self, ctx):
        """测试中文字符不会被错误匹配为用户名"""
        context = "用户: 你好\n助手: 你好！"
        entities = ctx._extract_entities_from_context(context)
        for e in entities:
            assert not any('\u4e00' <= c <= '\u9fff' for c in e)


class TestResolveReferences:
    """代词消解测试"""

    def test_resolves_this_to_recent_user(self, ctx):
        """测试'这个'能消解到最近创建的用户"""
        context = "用户: 创建一个新用户test333\n助手: test333 已创建"
        enhanced = ctx.resolve_references("修改一下这个密码，改成abc123", context)
        assert "test333" in enhanced

    def test_resolves_that(self, ctx):
        """测试'那个'能消解"""
        context = "用户: 查看 /home/test/file.txt\n助手: 文件内容..."
        enhanced = ctx.resolve_references("删掉那个文件", context)
        assert "file.txt" in enhanced or "/home/test" in enhanced

    def test_no_reference_unchanged(self, ctx):
        """测试无代词时输入不变"""
        original = "创建一个新用户testuser"
        assert ctx.resolve_references(original, "") == original

    def test_empty_context_unchanged(self, ctx):
        """测试空上下文时输入不变"""
        original = "修改一下这个密码"
        assert ctx.resolve_references(original, "") == original

    def test_no_entities_unchanged(self, ctx):
        """测试上下文无实体时输入不变"""
        original = "修改一下这个密码"
        context = "用户: 你好\n助手: 你好！"
        assert ctx.resolve_references(original, context) == original


class TestEnrichClarificationReply:
    """澄清回复增强测试"""

    def test_clarification_reply_username(self, ctx):
        """测试回答澄清问题：用户名"""
        context = (
            "用户: 修改一下这个密码，改成lzy@321\n"
            "助手: 你是想修改哪个用户的密码？请具体说明。"
        )
        enhanced, was_enriched = ctx.enrich_clarification_reply("test333", context)
        assert was_enriched is True
        assert "test333" in enhanced
        assert "密码" in enhanced

    def test_clarification_reply_with_password_params(self, ctx):
        """测试回答澄清问题：用户名（保留原密码参数）"""
        context = (
            "用户: 修改一下这个密码，改成lzy@321\n"
            "助手: 你是想修改哪个用户的密码？"
        )
        enhanced, was_enriched = ctx.enrich_clarification_reply("test333", context)
        assert was_enriched is True
        assert "test333" in enhanced
        # 应该保留原消息中的密码参数
        assert "lzy@321" in enhanced

    def test_not_clarification_reply(self, ctx):
        """测试非澄清回复不变"""
        context = (
            "用户: 创建一个新用户test333\n"
            "助手: 用户 test333 已成功创建"
        )
        enhanced, was_enriched = ctx.enrich_clarification_reply("test333", context)
        assert was_enriched is False

    def test_full_command_not_enriched(self, ctx):
        """测试完整命令不会被增强"""
        context = (
            "用户: 修改一下这个密码\n"
            "助手: 你是想修改哪个用户的密码？"
        )
        enhanced, was_enriched = ctx.enrich_clarification_reply("修改用户test333的密码为abc123", context)
        assert was_enriched is False

    def test_long_input_not_enriched(self, ctx):
        """测试长输入不会被增强"""
        context = (
            "用户: 修改一下这个密码\n"
            "助手: 你是想修改哪个用户的密码？"
        )
        long_input = "这是一个很长的输入" * 5
        enhanced, was_enriched = ctx.enrich_clarification_reply(long_input, context)
        assert was_enriched is False

    def test_empty_context_not_enriched(self, ctx):
        """测试空上下文不变"""
        enhanced, was_enriched = ctx.enrich_clarification_reply("test333", "")
        assert was_enriched is False

    def test_no_clarification_keywords(self, ctx):
        """测试助手回复不含澄清关键词时不变"""
        context = (
            "用户: 你好\n"
            "助手: 你好！有什么可以帮你的？"
        )
        enhanced, was_enriched = ctx.enrich_clarification_reply("test333", context)
        assert was_enriched is False

    def test_user_entity_clarification(self, ctx):
        """测试用户相关澄清（非密码场景）"""
        context = (
            "用户: 删掉那个用户\n"
            "助手: 请说明要删除哪个用户？"
        )
        enhanced, was_enriched = ctx.enrich_clarification_reply("testuser", context)
        assert was_enriched is True
        assert "testuser" in enhanced


class TestExtractTrailingParams:
    """尾部参数提取测试"""

    def test_extract_change_to(self, ctx):
        """测试提取'改成xxx'"""
        result = ctx._extract_trailing_params("修改一下这个密码，改成lzy@321")
        assert "lzy@321" in result

    def test_extract_new_password(self, ctx):
        """测试提取'新密码xxx'"""
        result = ctx._extract_trailing_params("设置新密码abc123")
        assert "abc123" in result

    def test_no_password_param(self, ctx):
        """测试无密码参数"""
        result = ctx._extract_trailing_params("创建一个新用户")
        assert result == ""


class TestFormatContext:
    """上下文格式化测试"""

    def test_format_empty(self, ctx):
        assert ctx.format_context([]) == ""

    def test_format_turns(self, ctx):
        turns = [
            ConversationTurn(timestamp="2026-01-01", user_input="你好", agent_response="你好！"),
            ConversationTurn(timestamp="2026-01-01", user_input="查看磁盘", agent_response="磁盘信息..."),
        ]
        result = ctx.format_context(turns)
        assert "用户: 你好" in result
        assert "用户: 查看磁盘" in result

    def test_format_order(self, ctx):
        """测试上下文按时间倒序排列（最新在前）"""
        turns = [
            ConversationTurn(timestamp="2026-01-01", user_input="第一条", agent_response="回复一"),
            ConversationTurn(timestamp="2026-01-01", user_input="第二条", agent_response="回复二"),
        ]
        result = ctx.format_context(turns)
        lines = result.strip().split("\n")
        # format_context 使用 reversed(turns)，所以最新的在前
        assert "第二条" in lines[0]
        assert "第一条" in lines[2]


class TestCompressContext:
    """上下文压缩测试"""

    def test_short_context_unchanged(self, ctx):
        short = "用户: 你好\n助手: 你好！"
        assert ctx.compress_context(short) == short

    def test_long_context_compressed(self):
        """测试长上下文超过 token 限制时被压缩"""
        ctx = ContextManager(max_tokens=100)
        lines = [f"用户: 这是第{i}条消息内容，需要足够长来超过token限制\n助手: 这是第{i}条回复内容" for i in range(20)]
        long_context = "\n".join(lines)
        compressed = ctx.compress_context(long_context)
        assert "已省略" in compressed


class TestEstimateTokens:
    """Token 估算测试"""

    def test_chinese_text(self, ctx):
        tokens = ctx._estimate_tokens("你好世界")
        assert tokens > 0

    def test_english_text(self, ctx):
        tokens = ctx._estimate_tokens("hello world")
        assert tokens > 0

    def test_empty_text(self, ctx):
        assert ctx._estimate_tokens("") == 0
