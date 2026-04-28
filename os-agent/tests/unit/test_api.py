"""API 接口测试"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """创建测试客户端"""
    from src.interface.server import app
    return TestClient(app)


class TestLearningAPI:
    """学习记忆 API 测试"""

    def test_get_learning_stats(self, client):
        """测试获取学习记忆统计"""
        response = client.get("/api/learning/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_lessons" in data
        assert "successful_fixes" in data
        assert "categories" in data

    def test_get_learning_lessons(self, client):
        """测试获取学习记忆列表"""
        response = client.get("/api/learning/lessons")
        assert response.status_code == 200
        data = response.json()
        assert "lessons" in data or isinstance(data, list)
        assert "success" in data

    def test_export_learning_markdown(self, client):
        """测试导出学习记忆 Markdown"""
        response = client.get("/api/learning/export")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "content" in data
        assert "OS Agent 学习记忆报告" in data["content"]

    def test_get_learning_lessons_with_limit(self, client):
        """测试分页获取学习记忆"""
        response = client.get("/api/learning/lessons?limit=10&offset=0")
        assert response.status_code == 200


class TestSudoAPI:
    """Sudo API 测试"""

    def test_sudo_status(self, client):
        """测试查询 sudo 状态"""
        response = client.get("/api/sudo/status")
        assert response.status_code == 200
        data = response.json()
        assert "has_sudo" in data

    def test_set_sudo_password_empty(self, client):
        """测试设置空密码"""
        response = client.post("/api/sudo/password", json={"password": ""})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False


class TestHealthAPI:
    """健康检查 API 测试"""

    def test_health_check(self, client):
        """测试健康检查"""
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_capabilities_list(self, client):
        """测试获取能力列表"""
        response = client.get("/api/capabilities")
        assert response.status_code == 200
        data = response.json()
        assert "capabilities" in data
        caps = data["capabilities"]
        assert isinstance(caps, list)
        cap_names = [cap["name"] for cap in caps]
        assert "disk" in cap_names
        assert "file" in cap_names


class TestChatAPI:
    """聊天 API 测试"""

    @patch("src.agent.core.OSIntelligentAgent.process")
    def test_chat_endpoint(self, mock_process, client):
        """测试聊天接口"""
        mock_process.return_value = MagicMock(
            success=True,
            message="磁盘使用率 45%",
            commands_executed=["df -h"],
            risk_level=MagicMock(value="low"),
            needs_confirmation=False,
            confirmation_prompt="",
            error=None,
            progress=None,
        )
        response = client.post("/api/chat", json={
            "message": "查看磁盘使用情况",
            "server_id": "local",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_chat_empty_message(self, client):
        """测试空消息"""
        response = client.post("/api/chat", json={
            "message": "",
            "server_id": "local",
        })
        # 空消息应该被处理（可能返回错误或闲聊回复）
        assert response.status_code == 200
