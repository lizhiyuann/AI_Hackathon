"""WebSocket实时通信"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import List

from src.agent.core import OSIntelligentAgent


class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_message(self, websocket: WebSocket, message: dict):
        await websocket.json(message)


manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点"""
    agent = OSIntelligentAgent()
    await manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            confirmed = data.get("confirmed", False)

            if not user_message:
                continue

            # 处理用户消息
            response = await agent.process(user_message, confirmed=confirmed)

            # 发送响应
            await manager.send_message(websocket, {
                "success": response.success,
                "message": response.message,
                "commands_executed": response.commands_executed,
                "risk_level": response.risk_level.value,
                "needs_confirmation": response.needs_confirmation,
            })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
