"""本地语音合成 - 基于edge-tts (微软免费TTS)"""
import tempfile
import os

from src.voice.base import TTSEngine
from src.agent.config import ConfigManager
from src.utils.logger import log


class LocalTTS(TTSEngine):
    """基于edge-tts的本地语音合成"""

    def __init__(self, config=None):
        self.config = config or ConfigManager().voice.tts

    async def synthesize(self, text: str) -> bytes:
        """将文本合成为音频"""
        try:
            import edge_tts

            communicate = edge_tts.Communicate(
                text,
                voice=self.config.voice,
                rate=self.config.rate,
                volume=self.config.volume,
                pitch=self.config.pitch,
            )

            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]

            log.debug(f"语音合成完成: {len(audio_data)} bytes")
            return audio_data

        except Exception as e:
            log.error(f"语音合成失败: {e}")
            raise

    async def synthesize_to_file(self, text: str, output_path: str) -> str:
        """将文本合成为音频并保存到文件"""
        try:
            import edge_tts

            communicate = edge_tts.Communicate(
                text,
                voice=self.config.voice,
                rate=self.config.rate,
                volume=self.config.volume,
                pitch=self.config.pitch,
            )

            await communicate.save(output_path)
            log.debug(f"语音合成保存到: {output_path}")
            return output_path

        except Exception as e:
            log.error(f"语音合成失败: {e}")
            raise

    async def list_voices(self) -> list:
        """列出所有可用发音人"""
        try:
            import edge_tts
            voices = await edge_tts.list_voices()
            chinese_voices = [v for v in voices if v["Locale"].startswith("zh-")]
            return chinese_voices
        except Exception as e:
            log.error(f"获取发音人列表失败: {e}")
            return []

    def is_available(self) -> bool:
        """检查引擎是否可用"""
        try:
            import edge_tts
            return True
        except ImportError:
            return False
