"""本地语音识别 - 基于faster-whisper"""
import tempfile
import os
from pathlib import Path

from src.voice.base import STTEngine
from src.agent.config import ConfigManager
from src.utils.logger import log


class LocalSTT(STTEngine):
    """基于faster-whisper的本地语音识别"""

    def __init__(self, config=None):
        self.config = config or ConfigManager().voice.stt
        self._model = None

    def _load_model(self):
        """加载模型"""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                self._model = WhisperModel(
                    self.config.model_size,
                    device=self.config.device,
                    compute_type=self.config.compute_type,
                )
                log.info(f"Whisper模型加载成功: {self.config.model_size}")
            except Exception as e:
                log.error(f"Whisper模型加载失败: {e}")
                raise

    async def recognize(self, audio_data: bytes) -> str:
        """识别音频为文本"""
        self._load_model()

        # 将音频数据写入临时文件
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        try:
            segments, info = self._model.transcribe(
                temp_path,
                language=self.config.language,
            )
            text = " ".join(seg.text for seg in segments)
            log.debug(f"语音识别结果: {text} (置信度: {info.language_probability:.2f})")
            return text.strip()
        finally:
            os.unlink(temp_path)

    async def recognize_from_file(self, file_path: str) -> str:
        """从文件识别音频"""
        self._load_model()

        segments, info = self._model.transcribe(
            file_path,
            language=self.config.language,
        )
        text = " ".join(seg.text for seg in segments)
        return text.strip()

    def is_available(self) -> bool:
        """检查引擎是否可用"""
        try:
            import faster_whisper
            return True
        except ImportError:
            return False
