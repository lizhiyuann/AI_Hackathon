"""学习记忆模块 - 助手自我进化，从错误修正中提取经验教训"""
import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from src.utils.logger import log


DATA_DIR = Path(__file__).parent.parent.parent / "data"


class LearningMemory:
    """学习记忆管理器 - 从执行失败和自动修正中提取经验，用于未来决策"""

    def __init__(self, db_path: Optional[str] = None):
        DATA_DIR.mkdir(exist_ok=True)
        self.db_path = db_path or str(DATA_DIR / "memory.db")
        self._init_tables()

    def _init_tables(self):
        """初始化学习记忆表"""
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS learning_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    category TEXT NOT NULL,
                    trigger_pattern TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    original_error TEXT,
                    correction_action TEXT,
                    correction_params TEXT,
                    success INTEGER DEFAULT 1,
                    use_count INTEGER DEFAULT 0,
                    last_used TEXT
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_learning_category
                ON learning_memory(category)
            """)
            db.commit()

    def save_lesson(
        self,
        category: str,
        trigger_pattern: str,
        lesson: str,
        original_error: str = "",
        correction_action: str = "",
        correction_params: Optional[Dict] = None,
        success: bool = True,
    ):
        """保存一条学习记忆

        Args:
            category: 分类，如 file_search, file_view, intent_parse 等
            trigger_pattern: 触发模式（关键词/正则），用于匹配类似场景
            lesson: 教训总结（自然语言）
            original_error: 原始错误信息
            correction_action: 修正后的 action
            correction_params: 修正后的参数
            success: 修正是否成功
        """
        now = datetime.now().isoformat()
        params_json = json.dumps(correction_params, ensure_ascii=False) if correction_params else None

        with sqlite3.connect(self.db_path) as db:
            # 检查是否已有高度相似的记忆（避免重复）
            existing = db.execute(
                "SELECT id, use_count FROM learning_memory WHERE category = ? AND trigger_pattern = ?",
                (category, trigger_pattern),
            ).fetchone()

            if existing:
                # 更新已有记忆
                db.execute(
                    """UPDATE learning_memory
                       SET lesson = ?, original_error = ?, correction_action = ?,
                           correction_params = ?, success = ?, last_used = ?, use_count = use_count + 1
                       WHERE id = ?""",
                    (lesson, original_error, correction_action, params_json, int(success), now, existing[0]),
                )
                log.info(f"更新学习记忆 #{existing[0]}: {trigger_pattern}")
            else:
                # 插入新记忆
                db.execute(
                    """INSERT INTO learning_memory
                       (timestamp, category, trigger_pattern, lesson, original_error,
                        correction_action, correction_params, success, last_used)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (now, category, trigger_pattern, lesson, original_error,
                     correction_action, params_json, int(success), now),
                )
                log.info(f"新增学习记忆: [{category}] {trigger_pattern}")

            db.commit()

        # 自动同步 md 文件，保持始终最新
        try:
            self.export_to_markdown(str(DATA_DIR / "learning_memory.md"))
        except Exception as e:
            log.debug(f"同步学习记忆 md 文件失败: {e}")

    def recall(self, query: str, category: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """根据查询召回相关学习记忆

        Args:
            query: 用户输入或场景描述
            category: 可选的分类过滤
            limit: 最多返回条数
        Returns:
            相关的学习记忆列表
        """
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row

            # 先按 category 过滤
            if category:
                rows = db.execute(
                    """SELECT * FROM learning_memory
                       WHERE category = ?
                       ORDER BY use_count DESC, last_used DESC
                       LIMIT ?""",
                    (category, limit),
                ).fetchall()
            else:
                rows = db.execute(
                    """SELECT * FROM learning_memory
                       ORDER BY use_count DESC, last_used DESC
                       LIMIT ?""",
                    (limit,),
                ).fetchall()

            results = []
            for row in rows:
                # 简单的关键词匹配：trigger_pattern 是否出现在 query 中
                if row["trigger_pattern"] and row["trigger_pattern"] in query:
                    results.insert(0, dict(row))  # 精确匹配放前面
                else:
                    results.append(dict(row))

            # 标记使用
            if results:
                now = datetime.now().isoformat()
                for r in results[:limit]:
                    db.execute(
                        "UPDATE learning_memory SET use_count = use_count + 1, last_used = ? WHERE id = ?",
                        (now, r["id"]),
                    )
                db.commit()

            return results[:limit]

    def get_all(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """获取所有学习记忆"""
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM learning_memory ORDER BY last_used DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_stats(self) -> Dict[str, Any]:
        """获取学习记忆统计"""
        with sqlite3.connect(self.db_path) as db:
            total = db.execute("SELECT COUNT(*) FROM learning_memory").fetchone()[0]
            success = db.execute("SELECT COUNT(*) FROM learning_memory WHERE success = 1").fetchone()[0]
            categories = db.execute(
                "SELECT category, COUNT(*) as cnt FROM learning_memory GROUP BY category ORDER BY cnt DESC"
            ).fetchall()
            return {
                "total_lessons": total,
                "successful_fixes": success,
                "categories": {row[0]: row[1] for row in categories},
            }

    def delete(self, lesson_id: int):
        """删除一条学习记忆"""
        with sqlite3.connect(self.db_path) as db:
            db.execute("DELETE FROM learning_memory WHERE id = ?", (lesson_id,))
            db.commit()

    def format_for_prompt(self, lessons: List[Dict[str, Any]]) -> str:
        """将学习记忆格式化为 LLM 提示词片段"""
        if not lessons:
            return ""

        parts = ["以下是助手从过去的错误中学习到的经验，供你参考："]
        for i, lesson in enumerate(lessons, 1):
            cat = lesson.get("category", "")
            trigger = lesson.get("trigger_pattern", "")
            lesson_text = lesson.get("lesson", "")
            correction = lesson.get("correction_action", "")
            success = "成功" if lesson.get("success") else "失败"
            parts.append(f"{i}. [{cat}] {trigger} → {lesson_text} (修正: {correction}, 结果: {success})")

        return "\n".join(parts)

    def export_to_markdown(self, output_path: Optional[str] = None) -> str:
        """导出全部学习记忆为 Markdown 文档

        Args:
            output_path: 输出文件路径，如果为 None 则返回字符串不写文件
        Returns:
            Markdown 内容字符串
        """
        lessons = self.get_all(limit=999)
        stats = self.get_stats()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if stats['total_lessons'] > 0:
            success_rate = f"{stats['successful_fixes'] / stats['total_lessons'] * 100:.1f}%"
        else:
            success_rate = "-"

        lines = [
            "# OS Agent 学习记忆报告",
            "",
            f"> 更新时间: {now}",
            "",
            "## 统计概览",
            "",
            "| 指标 | 数值 |",
            "|------|------|",
            f"| 总记录数 | {stats['total_lessons']} |",
            f"| 成功修正数 | {stats['successful_fixes']} |",
            f"| 成功率 | {success_rate} |",
            "",
            "### 分类分布",
            "",
        ]

        if stats["categories"]:
            lines.append("| 分类 | 数量 |")
            lines.append("|------|------|")
            for cat, cnt in stats["categories"].items():
                lines.append(f"| {cat} | {cnt} |")
        else:
            lines.append("暂无数据。")

        lines.extend(["", "## 记忆详情", ""])

        if not lessons:
            lines.append("暂无学习记忆记录。")
        else:
            for i, lesson in enumerate(lessons, 1):
                cat = lesson.get("category", "未分类")
                trigger = lesson.get("trigger_pattern", "-")
                lesson_text = lesson.get("lesson", "-")
                original_error = lesson.get("original_error", "")
                correction_action = lesson.get("correction_action", "")
                correction_params = lesson.get("correction_params", "")
                success = "是" if lesson.get("success") else "否"
                use_count = lesson.get("use_count", 0)
                timestamp = lesson.get("timestamp", "")
                last_used = lesson.get("last_used", "")

                lines.append(f"### {i}. [{cat}] {trigger}")
                lines.append("")
                lines.append(f"| 字段 | 内容 |")
                lines.append(f"|------|------|")
                lines.append(f"| 触发模式 | `{trigger}` |")
                lines.append(f"| 经验教训 | {lesson_text} |")
                if original_error:
                    lines.append(f"| 原始错误 | `{original_error[:120]}` |")
                if correction_action:
                    lines.append(f"| 修正操作 | `{correction_action}` |")
                if correction_params:
                    params_str = correction_params if isinstance(correction_params, str) else json.dumps(correction_params, ensure_ascii=False)
                    lines.append(f"| 修正参数 | `{params_str[:120]}` |")
                lines.append(f"| 修正成功 | {success} |")
                lines.append(f"| 使用次数 | {use_count} |")
                lines.append(f"| 创建时间 | {timestamp} |")
                lines.append(f"| 最后使用 | {last_used} |")
                lines.append("")

        content = "\n".join(lines)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(content, encoding="utf-8")
            log.info(f"学习记忆已导出到: {output_path}")

        return content


def extract_lesson_from_retry(
    user_input: str,
    original_intent: Dict,
    error: str,
    fix_hint: Dict,
    final_result_success: bool,
) -> Optional[Dict]:
    """从一次自动重试中提取学习教训

    Args:
        user_input: 用户原始输入
        original_intent: 原始意图解析结果
        error: 原始错误信息
        fix_hint: LLM 给出的修正方案
        final_result_success: 修正后是否成功
    Returns:
        学习教训字典，包含 category, trigger_pattern, lesson 等
    """
    try:
        from src.agent.llm import LLMFactory
        from src.agent.config import ConfigManager
        from langchain_core.messages import HumanMessage

        config = ConfigManager()
        llm = LLMFactory.create(config)

        prompt = f"""你是一个学习分析器。请从以下错误修正案例中提取一条简洁的经验教训。

用户输入：{user_input}
原始意图：{json.dumps(original_intent, ensure_ascii=False)}
错误信息：{error}
修正方案：{json.dumps(fix_hint, ensure_ascii=False)}
修正结果：{"成功" if final_result_success else "失败"}

请返回 JSON（只返回 JSON，不要其他内容）：
{{
  "category": "分类（如 file_search/file_view/intent_parse/command_exec）",
  "trigger_pattern": "触发关键词或模式（简洁，如'查找+目录路径'）",
  "lesson": "一句话经验教训（面向未来，如'当用户说查找某个路径且路径是目录时，应该用 list 而不是 view'）"
}}"""

        response = llm.invoke([HumanMessage(content=prompt)])
        text = response.content
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            lesson = json.loads(text[first_brace:last_brace + 1])
            lesson["original_error"] = error
            lesson["correction_action"] = fix_hint.get("action", "")
            lesson["correction_params"] = fix_hint.get("parameters")
            lesson["success"] = final_result_success
            return lesson
    except Exception as e:
        log.warning(f"提取学习教训失败: {e}")

    return None
