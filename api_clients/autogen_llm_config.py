"""
AutoGen LLM Configuration Builder
Supports cloud providers (OpenAI, Anthropic) and local models (Ollama, custom endpoints)
"""
from typing import List, Dict, Optional
import os
from utils.config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class AutoGenLLMConfig:
    """
    Builder for AutoGen config_list with support for:
    - Cloud providers: OpenAI, Anthropic
    - Local models: Ollama
    - Custom OpenAI-compatible endpoints
    - Hybrid mode: different models for different agents
    """

    def __init__(self, config: Config):
        self.config = config

    def build_config_list(self, agent_name: Optional[str] = None) -> List[Dict]:
        """
        Build config_list for AutoGen agents

        Args:
            agent_name: Name of the agent (for hybrid mode)

        Returns:
            List of LLM configurations for AutoGen
        """
        config_list = []

        # Hybrid mode: agent-specific models
        if self.config.get('llm.hybrid.enabled') and agent_name:
            agent_config = self._get_agent_specific_config(agent_name)
            if agent_config:
                logger.info(f"Using hybrid mode for agent '{agent_name}': {agent_config['model']}")
                config_list.append(agent_config)
                return config_list  # Only use agent-specific config in hybrid mode

        # Cloud: OpenAI
        if self.config.get('llm.cloud.openai.enabled', True):
            openai_config = self._build_openai_config()
            if openai_config:
                config_list.append(openai_config)

        # Cloud: Anthropic
        if self.config.get('llm.cloud.anthropic.enabled', False):
            anthropic_config = self._build_anthropic_config()
            if anthropic_config:
                config_list.append(anthropic_config)

        # Local: Ollama
        if self.config.get('llm.local.enabled', False):
            ollama_configs = self._build_ollama_configs()
            config_list.extend(ollama_configs)

        # Custom endpoint
        if self.config.get('llm.custom.enabled', False):
            custom_config = self._build_custom_config()
            if custom_config:
                config_list.append(custom_config)

        if not config_list:
            logger.warning("No LLM configurations enabled, using default OpenAI")
            # Fallback to default OpenAI
            api_key = self.config.get_api_key('openai')
            config_list.append({
                "model": "gpt-4",
                "api_key": api_key,
            })

        logger.info(f"Built config_list with {len(config_list)} LLM configurations")
        return config_list

    def _get_agent_specific_config(self, agent_name: str) -> Optional[Dict]:
        """Get configuration for specific agent in hybrid mode"""
        agent_models = self.config.get('llm.hybrid.agent_models', {})

        if agent_name not in agent_models:
            logger.warning(f"No hybrid config for agent '{agent_name}', using default")
            return None

        agent_config = agent_models[agent_name]
        provider = agent_config.get('provider')
        model = agent_config.get('model')

        if provider == 'openai':
            return {
                "model": model,
                "api_key": self.config.get_api_key('openai'),
            }
        elif provider == 'anthropic':
            return {
                "model": model,
                "api_key": self.config.get_api_key('anthropic'),
                "api_type": "anthropic",
            }
        elif provider == 'ollama':
            return {
                "model": model,
                "base_url": self.config.get('llm.local.ollama_base_url', 'http://localhost:11434/v1'),
                "api_key": "ollama",  # Dummy key for Ollama
            }
        else:
            logger.warning(f"Unknown provider '{provider}' for agent '{agent_name}'")
            return None

    def _build_openai_config(self) -> Optional[Dict]:
        """Build OpenAI configuration"""
        try:
            api_key = self.config.get_api_key('openai')
            model = self.config.get('llm.cloud.openai.model', 'gpt-4')

            return {
                "model": model,
                "api_key": api_key,
            }
        except Exception as e:
            logger.error(f"Failed to build OpenAI config: {e}")
            return None

    def _build_anthropic_config(self) -> Optional[Dict]:
        """Build Anthropic configuration"""
        try:
            api_key = self.config.get_api_key('anthropic')
            model = self.config.get('llm.cloud.anthropic.model', 'claude-3-5-sonnet-20241022')

            return {
                "model": model,
                "api_key": api_key,
                "api_type": "anthropic",
            }
        except Exception as e:
            logger.error(f"Failed to build Anthropic config: {e}")
            return None

    def _build_ollama_configs(self) -> List[Dict]:
        """Build Ollama configurations for all specified models"""
        configs = []
        base_url = self.config.get('llm.local.ollama_base_url', 'http://localhost:11434/v1')
        models = self.config.get('llm.local.ollama_models', ['llama3.1', 'mistral'])

        for model in models:
            configs.append({
                "model": model,
                "base_url": base_url,
                "api_key": "ollama",  # Dummy key, Ollama doesn't require authentication
            })
            logger.info(f"Added Ollama model: {model} at {base_url}")

        return configs

    def _build_custom_config(self) -> Optional[Dict]:
        """Build custom OpenAI-compatible endpoint configuration"""
        base_url = self.config.get('llm.custom.base_url')
        model = self.config.get('llm.custom.model')
        api_key = self.config.get('llm.custom.api_key', '')

        if not base_url or not model:
            logger.warning("Custom LLM enabled but base_url or model not configured")
            return None

        return {
            "model": model,
            "base_url": base_url,
            "api_key": api_key or "custom",
        }

    def get_provider_info(self) -> Dict:
        """Get information about configured providers"""
        return {
            "openai": self.config.get('llm.cloud.openai.enabled', True),
            "anthropic": self.config.get('llm.cloud.anthropic.enabled', False),
            "ollama": self.config.get('llm.local.enabled', False),
            "custom": self.config.get('llm.custom.enabled', False),
            "hybrid_mode": self.config.get('llm.hybrid.enabled', False),
        }


def create_autogen_llm_config(config: Config) -> AutoGenLLMConfig:
    """
    Factory function to create AutoGenLLMConfig

    Args:
        config: Config object

    Returns:
        AutoGenLLMConfig instance
    """
    return AutoGenLLMConfig(config)
