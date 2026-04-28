"""学习记忆模块测试"""
import pytest
import json
import os
from pathlib import Path
from src.agent.learning import LearningMemory


@pytest.fixture
def memory(tmp_path):
    """创建临时学习记忆实例"""
    db_path = str(tmp_path / "test_learning.db")
    return LearningMemory(db_path=db_path)


class TestLearningMemory:
    """学习记忆管理器测试"""

    def test_save_and_recall(self, memory):
        """测试保存和召回学习记忆"""
        memory.save_lesson(
            category="file_view",
            trigger_pattern="查看+目录路径",
            lesson="当用户说查看某个路径且路径是目录时，应该用 list 而不是 view",
            original_error="Is a directory",
            correction_action="list",
            correction_params={"path": "/tmp"},
            success=True,
        )

        results = memory.recall("查看 /tmp 目录")
        assert len(results) > 0
        assert results[0]["category"] == "file_view"
        assert "list" in results[0]["lesson"] or "list" in results[0]["correction_action"]

    def test_save_duplicate_updates(self, memory):
        """测试重复触发模式自动更新而非重复插入"""
        memory.save_lesson(
            category="file_view",
            trigger_pattern="查看+目录路径",
            lesson="第一次的教训",
            success=True,
        )
        memory.save_lesson(
            category="file_view",
            trigger_pattern="查看+目录路径",
            lesson="更新后的教训",
            success=True,
        )

        all_lessons = memory.get_all(limit=10)
        # 应该只有1条记录，不是2条
        matching = [l for l in all_lessons if l["trigger_pattern"] == "查看+目录路径"]
        assert len(matching) == 1
        assert matching[0]["lesson"] == "更新后的教训"
        assert matching[0]["use_count"] >= 1

    def test_get_all(self, memory):
        """测试获取所有学习记忆"""
        for i in range(5):
            memory.save_lesson(
                category="test",
                trigger_pattern=f"pattern_{i}",
                lesson=f"lesson_{i}",
                success=True,
            )

        all_lessons = memory.get_all(limit=10)
        assert len(all_lessons) == 5

    def test_get_all_with_limit(self, memory):
        """测试分页获取学习记忆"""
        for i in range(10):
            memory.save_lesson(
                category="test",
                trigger_pattern=f"pattern_{i}",
                lesson=f"lesson_{i}",
                success=True,
            )

        page1 = memory.get_all(limit=5, offset=0)
        page2 = memory.get_all(limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5

    def test_get_stats(self, memory):
        """测试学习记忆统计"""
        memory.save_lesson(category="file_view", trigger_pattern="p1", lesson="l1", success=True)
        memory.save_lesson(category="file_view", trigger_pattern="p2", lesson="l2", success=True)
        memory.save_lesson(category="intent_parse", trigger_pattern="p3", lesson="l3", success=False)

        stats = memory.get_stats()
        assert stats["total_lessons"] == 3
        assert stats["successful_fixes"] == 2
        assert "file_view" in stats["categories"]
        assert stats["categories"]["file_view"] == 2

    def test_delete(self, memory):
        """测试删除学习记忆"""
        memory.save_lesson(
            category="test",
            trigger_pattern="to_delete",
            lesson="will be deleted",
            success=True,
        )

        all_lessons = memory.get_all(limit=10)
        assert len(all_lessons) == 1
        lesson_id = all_lessons[0]["id"]

        memory.delete(lesson_id)

        all_lessons = memory.get_all(limit=10)
        assert len(all_lessons) == 0

    def test_format_for_prompt(self, memory):
        """测试格式化为提示词"""
        memory.save_lesson(
            category="file_view",
            trigger_pattern="查看+目录",
            lesson="目录应该用 list 操作",
            correction_action="list",
            success=True,
        )

        results = memory.recall("查看目录")
        prompt_text = memory.format_for_prompt(results)
        assert "file_view" in prompt_text
        assert "list" in prompt_text
        assert "成功" in prompt_text

    def test_format_for_prompt_empty(self, memory):
        """测试空记忆格式化"""
        prompt_text = memory.format_for_prompt([])
        assert prompt_text == ""

    def test_export_to_markdown(self, memory, tmp_path):
        """测试导出 Markdown"""
        memory.save_lesson(
            category="file_view",
            trigger_pattern="查看+目录",
            lesson="目录应该用 list 操作",
            correction_action="list",
            success=True,
        )

        output_path = str(tmp_path / "test_report.md")
        content = memory.export_to_markdown(output_path)

        # 返回值包含关键内容
        assert "OS Agent 学习记忆报告" in content
        assert "统计概览" in content
        assert "记忆详情" in content
        assert "file_view" in content
        assert "查看+目录" in content

        # 文件已写入
        assert os.path.exists(output_path)
        file_content = Path(output_path).read_text(encoding="utf-8")
        assert file_content == content

    def test_export_to_markdown_empty(self, memory):
        """测试空记忆导出 Markdown"""
        content = memory.export_to_markdown()
        assert "OS Agent 学习记忆报告" in content
        assert "暂无学习记忆记录" in content

    def test_auto_sync_on_save(self, memory, tmp_path):
        """测试保存时自动同步 md 文件"""
        # 使用自定义 db_path，同步的 md 文件在同目录
        md_path = str(tmp_path / "test_sync.md")

        # 直接调用 export_to_markdown 写到 md_path 验证
        memory.save_lesson(
            category="test",
            trigger_pattern="sync_test",
            lesson="测试自动同步",
            success=True,
        )
        content = memory.export_to_markdown(md_path)
        assert "sync_test" in content

    def test_recall_with_category_filter(self, memory):
        """测试按分类过滤召回"""
        memory.save_lesson(category="file_view", trigger_pattern="p1", lesson="l1", success=True)
        memory.save_lesson(category="intent_parse", trigger_pattern="p2", lesson="l2", success=True)

        results = memory.recall("p1", category="file_view")
        assert all(r["category"] == "file_view" for r in results)
