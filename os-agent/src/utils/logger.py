"""日志工具模块"""
import sys
from loguru import logger
from src.agent.config import ConfigManager


def setup_logger():
    """配置日志系统"""
    config = ConfigManager()
    
    # 移除默认处理器
    logger.remove()
    
    # 添加控制台输出
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=config.app.log_level,
        colorize=True,
    )
    
    # 添加文件输出
    logger.add(
        "data/logs/app.log",
        rotation="10 MB",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        encoding="utf-8",
    )
    
    return logger


# 初始化日志
log = setup_logger()
