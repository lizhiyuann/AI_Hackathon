"""对话记忆模块 - SQLite持久化存储（支持会话管理）"""
import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from src.agent.models import ConversationTurn, Intent


# 数据存储目录
DATA_DIR = Path(__file__).parent.parent.parent / "data"


class ConversationMemory:
    """对话记忆管理器（支持多会话）"""

    def __init__(self, db_path: Optional[str] = None):
        DATA_DIR.mkdir(exist_ok=True)
        self.db_path = db_path or str(DATA_DIR / "memory.db")
        self._init_tables()

    def _init_tables(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as db:
            # 会话表
            db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '新会话',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # 对话记录表（增加 session_id）
            db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    timestamp TEXT NOT NULL,
                    user_input TEXT NOT NULL,
                    agent_response TEXT NOT NULL,
                    intent_json TEXT,
                    commands_executed TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            # 兼容旧表：如果没有 session_id 列就加上
            try:
                db.execute("SELECT session_id FROM conversations LIMIT 1")
            except sqlite3.OperationalError:
                db.execute("ALTER TABLE conversations ADD COLUMN session_id TEXT")
            db.commit()

    def create_session(self, session_id: str, title: str = "新会话") -> Dict[str, Any]:
        """创建新会话"""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title, now, now),
            )
            db.commit()
        return {"id": session_id, "title": title, "created_at": now, "updated_at": now}

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """列出所有会话（按更新时间倒序）"""
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            cursor = db.execute(
                "SELECT s.*, COUNT(c.id) as message_count FROM sessions s "
                "LEFT JOIN conversations c ON s.id = c.session_id "
                "GROUP BY s.id ORDER BY s.updated_at DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "title": row["title"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "message_count": row["message_count"],
                }
                for row in rows
            ]

    def get_session_messages(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取指定会话的消息列表"""
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            if session_id == "default":
                # 默认会话：session_id 为 NULL 或 'default' 的消息
                cursor = db.execute(
                    "SELECT * FROM conversations WHERE session_id IS NULL OR session_id = 'default' ORDER BY id ASC LIMIT ?",
                    (limit,),
                )
            else:
                cursor = db.execute(
                    "SELECT * FROM conversations WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                    (session_id, limit),
                )
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "user_input": row["user_input"],
                    "agent_response": row["agent_response"],
                    "commands": json.loads(row["commands_executed"] or "[]"),
                }
                for row in rows
            ]

    def update_session_title(self, session_id: str, title: str):
        """更新会话标题"""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, now, session_id),
            )
            db.commit()

    def delete_session(self, session_id: str):
        """删除会话及其消息"""
        with sqlite3.connect(self.db_path) as db:
            db.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
            db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            db.commit()

    def auto_title_from_input(self, text: str) -> str:
        """从用户输入生成简短的会话标题"""
        title = text.strip()[:20]
        if len(text.strip()) > 20:
            title += "..."
        return title or "新会话"

    def add(self, turn: ConversationTurn, session_id: Optional[str] = None):
        """添加对话记录"""
        now = turn.timestamp or datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT INTO conversations (session_id, timestamp, user_input, agent_response, intent_json, commands_executed) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    now,
                    turn.user_input,
                    turn.agent_response,
                    json.dumps(turn.intent.__dict__) if turn.intent else None,
                    json.dumps(turn.commands),
                ),
            )
            # 更新会话的 updated_at
            if session_id:
                db.execute(
                    "UPDATE sessions SET updated_at = ? WHERE id = ?",
                    (now, session_id),
                )
            db.commit()

    def get_recent(self, n: int = 5, session_id: Optional[str] = None) -> List[ConversationTurn]:
        """获取最近N条对话"""
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            if session_id:
                cursor = db.execute(
                    "SELECT * FROM conversations WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                    (session_id, n),
                )
            else:
                cursor = db.execute(
                    "SELECT * FROM conversations ORDER BY id DESC LIMIT ?", (n,)
                )
            rows = cursor.fetchall()
            return [
                ConversationTurn(
                    timestamp=row["timestamp"],
                    user_input=row["user_input"],
                    agent_response=row["agent_response"],
                    commands=json.loads(row["commands_executed"] or "[]"),
                )
                for row in reversed(rows)
            ]

    def search(self, query: str, limit: int = 10) -> List[ConversationTurn]:
        """搜索历史对话"""
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            cursor = db.execute(
                "SELECT * FROM conversations WHERE user_input LIKE ? OR agent_response LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit),
            )
            rows = cursor.fetchall()
            return [
                ConversationTurn(
                    timestamp=row["timestamp"],
                    user_input=row["user_input"],
                    agent_response=row["agent_response"],
                    commands=json.loads(row["commands_executed"] or "[]"),
                )
                for row in rows
            ]

    def get_context(self, window: int = 5, session_id: Optional[str] = None) -> str:
        """获取最近N轮对话上下文"""
        recent = self.get_recent(window, session_id=session_id)
        if not recent:
            return ""

        context_parts = []
        for turn in reversed(recent):
            context_parts.append(f"用户: {turn.user_input}")
            context_parts.append(f"助手: {turn.agent_response}")

        return "\n".join(context_parts)

    def clear(self, session_id: Optional[str] = None):
        """清空对话历史"""
        with sqlite3.connect(self.db_path) as db:
            if session_id:
                db.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
            else:
                db.execute("DELETE FROM conversations")
            db.commit()
