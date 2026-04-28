"""配置管理模块"""
import os
import yaml
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any
from dotenv import load_dotenv


load_dotenv()


# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "configs"


def resolve_env_vars(value: str) -> str:
    """解析环境变量引用 ${VAR_NAME}"""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        return os.getenv(env_var, value)
    return value


class AppConfig(BaseModel):
    """应用配置"""
    name: str = "OS Agent"
    version: str = "1.0.0"
    language: str = "zh-CN"
    log_level: str = "INFO"


class AgentConfig(BaseModel):
    """代理配置"""
    max_conversation_turns: int = 50
    max_command_length: int = 1000
    command_timeout: int = 30


class ConnectorConfig(BaseModel):
    """连接器配置"""
    mode: str = "local"
    remote_host: str = ""
    remote_port: int = 22
    remote_username: str = ""
    remote_key_path: str = ""


class InterfaceConfig(BaseModel):
    """界面配置"""
    cli_enabled: bool = True
    web_enabled: bool = True
    web_host: str = "0.0.0.0"
    web_port: int = 8000


class LLMProviderConfig(BaseModel):
    """LLM厂商配置"""
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    secret_key: str = ""


class LLMConfig(BaseModel):
    """大模型配置"""
    active_provider: str = "deepseek"
    providers: Dict[str, LLMProviderConfig] = Field(default_factory=dict)


class VoiceSTTConfig(BaseModel):
    """语音识别配置"""
    engine: str = "local"
    model_size: str = "base"
    device: str = "cpu"
    language: str = "zh"
    compute_type: str = "int8"


class VoiceTTSConfig(BaseModel):
    """语音合成配置"""
    engine: str = "local"
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate: str = "+0%"
    volume: str = "+0%"
    pitch: str = "+0Hz"


class VoiceConfig(BaseModel):
    """语音配置"""
    stt: VoiceSTTConfig = Field(default_factory=VoiceSTTConfig)
    tts: VoiceTTSConfig = Field(default_factory=VoiceTTSConfig)


class ConfigManager:
    """配置管理器 - 单例模式"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._load_configs()

    def _load_configs(self):
        """加载所有配置文件"""
        # 加载应用配置
        app_data = self._load_yaml("app.yaml")
        self.app = AppConfig(**app_data.get("app", {}))
        self.agent = AgentConfig(**app_data.get("agent", {}))
        self.connector = ConnectorConfig(
            mode=app_data.get("connector", {}).get("mode", "local"),
            remote_host=app_data.get("connector", {}).get("remote", {}).get("host", ""),
            remote_port=app_data.get("connector", {}).get("remote", {}).get("port", 22),
            remote_username=app_data.get("connector", {}).get("remote", {}).get("username", ""),
            remote_key_path=app_data.get("connector", {}).get("remote", {}).get("key_path", ""),
        )
        self.interface = InterfaceConfig(
            cli_enabled=app_data.get("interface", {}).get("cli", {}).get("enabled", True),
            web_enabled=app_data.get("interface", {}).get("web", {}).get("enabled", True),
            web_host=app_data.get("interface", {}).get("web", {}).get("host", "0.0.0.0"),
            web_port=app_data.get("interface", {}).get("web", {}).get("port", 8000),
        )

        # 加载LLM配置
        llm_data = self._load_yaml("llm.yaml")
        providers = {}
        for name, provider_data in llm_data.get("providers", {}).items():
            resolved = {}
            for k, v in provider_data.items():
                resolved[k] = resolve_env_vars(v) if isinstance(v, str) else v
            providers[name] = LLMProviderConfig(**resolved)

        self.llm = LLMConfig(
            active_provider=llm_data.get("active_provider", "deepseek"),
            providers=providers,
        )

        # 加载语音配置
        voice_data = self._load_yaml("voice.yaml")
        stt_data = voice_data.get("stt", {})
        tts_data = voice_data.get("tts", {})
        local_stt = stt_data.get("local", {})
        local_tts = tts_data.get("local", {})

        self.voice = VoiceConfig(
            stt=VoiceSTTConfig(
                engine=stt_data.get("engine", "local"),
                model_size=local_stt.get("model_size", "base"),
                device=local_stt.get("device", "cpu"),
                language=local_stt.get("language", "zh"),
                compute_type=local_stt.get("compute_type", "int8"),
            ),
            tts=VoiceTTSConfig(
                engine=tts_data.get("engine", "local"),
                voice=local_tts.get("voice", "zh-CN-XiaoxiaoNeural"),
                rate=local_tts.get("rate", "+0%"),
                volume=local_tts.get("volume", "+0%"),
                pitch=local_tts.get("pitch", "+0Hz"),
            ),
        )

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """加载YAML配置文件"""
        config_path = CONFIG_DIR / filename
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def get_active_llm_config(self) -> LLMProviderConfig:
        """获取当前激活的LLM配置"""
        provider = self.llm.active_provider
        return self.llm.providers.get(provider, LLMProviderConfig())
