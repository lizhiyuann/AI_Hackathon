"""远程STT API引擎 - 支持多厂商"""
from src.voice.base import STTEngine
from src.agent.config import ConfigManager
from src.utils.logger import log


class RemoteSTT(STTEngine):
    """远程语音识别引擎 - 支持阿里云/百度/讯飞"""

    def __init__(self, provider: str = None, config=None):
        cm = config or ConfigManager()
        self.provider = provider or cm.voice.stt.api.provider if hasattr(cm.voice.stt, 'api') else "aliyun"
        self._config = config

    async def recognize(self, audio_data: bytes) -> str:
        """通过API识别音频"""
        if self.provider == "aliyun":
            return await self._recognize_aliyun(audio_data)
        elif self.provider == "baidu":
            return await self._recognize_baidu(audio_data)
        elif self.provider == "xunfei":
            return await self._recognize_xunfei(audio_data)
        else:
            raise ValueError(f"不支持的语音识别提供商: {self.provider}")

    async def _recognize_aliyun(self, audio_data: bytes) -> str:
        """阿里云语音识别"""
        try:
            import nls
            # 阿里云NLS SDK调用逻辑
            log.info("使用阿里云语音识别")
            return ""
        except ImportError:
            log.error("请安装阿里云NLS SDK: pip install alibabacloud-nls")
            raise

    async def _recognize_baidu(self, audio_data: bytes) -> str:
        """百度语音识别"""
        try:
            from aip import AipSpeech
            log.info("使用百度语音识别")
            return ""
        except ImportError:
            log.error("请安装百度AI SDK: pip install baidu-aip")
            raise

    async def _recognize_xunfei(self, audio_data: bytes) -> str:
        """讯飞语音识别"""
        log.info("使用讯飞语音识别")
        return ""

    def is_available(self) -> bool:
        return True
