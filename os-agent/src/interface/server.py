"""Web服务 - FastAPI"""
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from src.agent.config import ConfigManager
from src.interface.api import router as api_router
from src.interface.websocket import websocket_endpoint
from src.utils.logger import log

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    config = ConfigManager()

    app = FastAPI(
        title="OS Agent API",
        description="操作系统智能代理API",
        version=config.app.version,
    )

    # 配置CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册API路由
    app.include_router(api_router)

    # WebSocket路由
    app.add_api_websocket_route("/ws", websocket_endpoint)

    # 前端构建目录 (Vite默认输出到 dist)
    frontend_build_dir = PROJECT_ROOT / "frontend" / "dist"

    # 根路径返回前端页面
    @app.get("/")
    async def serve_frontend():
        """返回前端页面"""
        index_path = frontend_build_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"message": "前端未构建，请先运行 npm run build"}

    # 静态文件服务 (JS, CSS, Assets)
    if frontend_build_dir.exists():
        # Vite构建后的JS和CSS在 assets 目录
        assets_dir = frontend_build_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static_assets")
        
        # 处理其他静态资源 (如 favicon.ico, vite.svg 等)
        @app.get("/{file_path:path}")
        async def serve_static_files(file_path: str):
            # 排除 API 和 WebSocket 路径，避免拦截后端路由
            if file_path.startswith("api/") or file_path.startswith("ws"):
                return JSONResponse(status_code=404, content={"message": "Not Found"})
            # 尝试在 dist 根目录查找文件（防止路径遍历攻击）
            file_full_path = (frontend_build_dir / file_path).resolve()
            if not str(file_full_path).startswith(str(frontend_build_dir.resolve())):
                return JSONResponse(status_code=403, content={"message": "Forbidden"})
            if file_full_path.exists() and file_full_path.is_file():
                return FileResponse(str(file_full_path))
            # 否则返回 index.html (支持 React Router 的 history 模式)
            index_path = frontend_build_dir / "index.html"
            if index_path.exists():
                return FileResponse(str(index_path))
            return JSONResponse(status_code=404, content={"message": "Not Found"})

    @app.on_event("startup")
    async def startup():
        # 重置服务器状态 - 确保每次启动只有本地服务器
        from src.interface import api
        api._servers_info = {
            "local": {
                "id": "local",
                "name": "本地服务器",
                "host": "localhost",
                "port": 22,
                "username": "",
                "auth_type": "password",
                "key_path": "",
                "status": "connected",
                "os_name": "",
                "distro_name": "",
            }
        }
        api._remote_executors = {}
        api._agents = {}
        
        # 重新加载安全规则和能力注册（确保配置文件生效）
        from src.guardian.rules import SecurityRules
        SecurityRules._instance = None  # 重置单例
        rules = SecurityRules()
        log.info(f"安全规则已加载: 保护路径{len(rules.protected_paths)}个, 高危模式{len(rules.high_risk_patterns)}个")
        
        from src.capabilities.registry import CapabilityRegistry
        CapabilityRegistry._instance = None
        CapabilityRegistry()
        log.info("能力注册中心已重新加载")
        
        log.info(f"OS Agent Web服务启动")
        if frontend_build_dir.exists():
            log.info(f"前端目录: {frontend_build_dir}")
        else:
            log.warning(f"前端构建目录不存在: {frontend_build_dir}，请先运行 npm run build")
        
        log.info(f"访问地址: http://{config.interface.web_host}:{config.interface.web_port}")

    @app.on_event("shutdown")
    async def shutdown():
        log.info("OS Agent Web服务停止")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    config = ConfigManager()
    uvicorn.run(
        "src.interface.server:app",
        host=config.interface.web_host,
        port=config.interface.web_port,
        reload=True,
    )
