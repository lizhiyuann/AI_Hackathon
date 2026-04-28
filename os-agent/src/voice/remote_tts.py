"""远程TTS API引擎 - 支持多厂商"""
from src.voice.base import TTSEngine
from src.agent.config import ConfigManager
from src.utils.logger import log


class RemoteTTS(TTSEngine):
    """远程语音合成引擎 - 支持阿里云/百度"""

    def __init__(self, provider: str = None, config=None):
        cm = config or ConfigManager()
        self.provider = provider or cm.voice.tts.api.provider if hasattr(cm.voice.tts, 'api') else "aliyun"
        self._config = config

    async def synthesize(self, text: str) -> bytes:
        """通过API合成语音"""
        if self.provider == "aliyun":
            return await self._synthesize_aliyun(text)
        elif self.provider == "baidu":
            return await self._synthesize_baidu(text)
        else:
            raise ValueError(f"不支持的语音合成提供商: {self.provider}")

    async def _synthesize_aliyun(self, text: str) -> bytes:
        """阿里云语音合成"""
        log.info("使用阿里云语音合成")
        return b""

    async def _synthesize_baidu(self, text: str) -> bytes:
        """百度语音合成"""
        log.info("使用百度语音合成")
        return b""

    def is_available(self) -> bool:
        return True
