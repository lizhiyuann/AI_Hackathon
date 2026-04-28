"""大模型统一调用接口 - 支持多厂商配置化切换"""
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from src.agent.config import ConfigManager, LLMProviderConfig
from src.utils.logger import log


class LLMFactory:
    """大模型工厂 - 根据配置创建对应LLM实例"""

    @staticmethod
    def create(config_manager: Optional[ConfigManager] = None) -> BaseChatModel:
        """创建LLM实例"""
        if config_manager is None:
            config_manager = ConfigManager()

        provider_name = config_manager.llm.active_provider
        provider_config = config_manager.get_active_llm_config()

        return LLMFactory._create_by_provider(provider_name, provider_config)

    @staticmethod
    def _create_by_provider(provider_name: str, config: LLMProviderConfig) -> BaseChatModel:
        """根据厂商名称创建对应的LLM实例"""

        if provider_name == "wenxin":
            # 文心一言 - 使用OpenAI兼容接口
            return ChatOpenAI(
                model=config.model,
                api_key=config.api_key,
                base_url="https://qianfan.baidubce.com/v2",
            )

        elif provider_name == "tongyi":
            # 通义千问 - 使用OpenAI兼容接口
            return ChatOpenAI(
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )

        else:
            # OpenAI兼容格式的厂商
            # deepseek, zhipu, moonshot, baichuan, yi, openai
            return ChatOpenAI(
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )

    @staticmethod
    def list_providers(config_manager: Optional[ConfigManager] = None) -> list:
        """列出所有可用的LLM厂商"""
        if config_manager is None:
            config_manager = ConfigManager()
        return list(config_manager.llm.providers.keys())

    @staticmethod
    def switch_provider(provider_name: str, config_manager: Optional[ConfigManager] = None) -> BaseChatModel:
        """切换LLM厂商"""
        if config_manager is None:
            config_manager = ConfigManager()

        if provider_name not in config_manager.llm.providers:
            raise ValueError(f"未知的LLM厂商: {provider_name}")

        config_manager.llm.active_provider = provider_name
        return LLMFactory.create(config_manager)
