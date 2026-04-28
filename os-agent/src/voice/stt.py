"""语音识别模块 - 使用vosk离线识别引擎"""
import json
import os
import io
import wave
from typing import Optional
from src.utils.logger import log


class SpeechToText:
    """语音转文字 - 基于vosk离线模型"""

    def __init__(self):
        self._model = None
        self._model_path = self._find_model()
        if self._model_path:
            log.info(f"vosk模型路径: {self._model_path}")
        else:
            log.warning("未找到vosk语音识别模型，语音识别功能不可用")

    def _find_model(self) -> Optional[str]:
        """查找vosk模型目录"""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        models_dir = os.path.join(base_dir, "models")

        if not os.path.isdir(models_dir):
            log.warning(f"模型目录不存在: {models_dir}")
            return None

        # 查找vosk模型目录
        for item in os.listdir(models_dir):
            if item.startswith("vosk-model"):
                full_path = os.path.join(models_dir, item)
                if os.path.isdir(full_path):
                    # 验证模型文件存在（支持新旧两种目录结构）
                    has_model = (
                        os.path.exists(os.path.join(full_path, "final.mdl"))
                        or os.path.exists(os.path.join(full_path, "am", "final.mdl"))
                    )
                    log.info(f"检查模型目录: {full_path}, 有效: {has_model}")
                    if has_model:
                        return full_path

        log.warning(f"在 {models_dir} 中未找到有效的vosk模型")
        return None

    def _load_model(self):
        """延迟加载模型"""
        if self._model is not None:
            return True
        if not self._model_path:
            return False
        try:
            from vosk import Model
            log.info("正在加载vosk语音识别模型...")
            self._model = Model(self._model_path)
            log.info("vosk模型加载完成")
            return True
        except Exception as e:
            log.error(f"加载vosk模型失败: {e}")
            return False

    def recognize(self, audio_data: bytes) -> str:
        """识别音频数据（WAV格式，16kHz，单声道，16bit PCM）

        Args:
            audio_data: WAV格式的音频字节数据

        Returns:
            识别出的文字
        """
        if not self._load_model():
            log.error("语音识别模型未加载")
            return ""

        try:
            from vosk import KaldiRecognizer

            # 解析WAV数据
            wf = wave.open(io.BytesIO(audio_data), "rb")

            # 验证音频格式
            if wf.getnchannels() != 1:
                log.warning(f"音频声道数为{wf.getnchannels()}，期望单声道")
            if wf.getsampwidth() != 2:
                log.warning(f"音频采样位数为{wf.getsampwidth() * 8}，期望16bit")

            sample_rate = wf.getframerate()
            log.info(f"音频信息: 采样率={sample_rate}, 声道={wf.getnchannels()}, "
                     f"采样位数={wf.getsampwidth() * 8}, 帧数={wf.getnframes()}")

            rec = KaldiRecognizer(self._model, sample_rate)
            rec.SetWords(True)

            results = []
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").strip()
                    if text:
                        results.append(text)

            # 获取最后部分
            final_result = json.loads(rec.FinalResult())
            final_text = final_result.get("text", "").strip()
            if final_text:
                results.append(final_text)

            full_text = " ".join(results).strip()
            log.info(f"语音识别结果: '{full_text}'")
            return full_text

        except Exception as e:
            log.error(f"语音识别失败: {e}")
            return ""

    @property
    def is_available(self) -> bool:
        """检查语音识别是否可用"""
        return self._model_path is not None


_stt: Optional[SpeechToText] = None

def get_stt() -> SpeechToText:
    """获取语音识别实例（单例）"""
    global _stt
    if _stt is None:
        _stt = SpeechToText()
    return _stt
