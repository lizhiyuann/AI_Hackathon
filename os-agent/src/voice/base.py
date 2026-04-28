"""语音引擎基类"""
from abc import ABC, abstractmethod


class STTEngine(ABC):
    """语音识别引擎基类 (STT - Speech To Text)"""

    @abstractmethod
    async def recognize(self, audio_data: bytes) -> str:
        """识别音频为文本"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查引擎是否可用"""
        pass


class TTSEngine(ABC):
    """语音合成引擎基类 (TTS - Text To Speech)"""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """将文本合成为音频"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查引擎是否可用"""
        pass
