"""
Configuration management for 3D Agent Generation System
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration manager"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self._config = self._load_config()
        self._load_api_keys_from_env()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        return config

    def _load_api_keys_from_env(self):
        """Load API keys and service URLs from environment variables (overrides config.yaml)"""
        # API keys
        env_mapping = {
            'tripo': 'TRIPO_API_KEY',
            'meshy': 'MESHY_API_KEY',
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'replicate': 'REPLICATE_API_TOKEN'
        }
        for key, env_var in env_mapping.items():
            env_value = os.getenv(env_var)
            if env_value:
                self._config['api_keys'][key] = env_value

        # Service URLs — allow Docker service names to override localhost defaults
        ollama_url = os.getenv('OLLAMA_BASE_URL')
        if ollama_url:
            self.set('llm.local.ollama_base_url', ollama_url)

        comfyui_url = os.getenv('COMFYUI_URL')
        if comfyui_url:
            models = self._config.get('default_settings', {}) \
                                  .get('local_image_models', {}) \
                                  .get('available_models', [])
            for m in models:
                if m.get('mode') == 'comfyui':
                    m['docker_url'] = comfyui_url

        hunyuan3d_url = os.getenv('HUNYUAN3D_URL')
        if hunyuan3d_url:
            models = self._config.get('default_settings', {}) \
                                  .get('local_3d_models', {}) \
                                  .get('available_models', [])
            for m in models:
                if m.get('name') == 'hunyuan3d':
                    m['docker_url'] = hunyuan3d_url

    def get(self, key_path: str, default=None):
        """
        Get configuration value by dot-separated path

        Example:
            config.get('api_keys.openai')
            config.get('default_settings.generation.api_provider')
        """
        keys = key_path.split('.')
        value = self._config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def set(self, key_path: str, value: Any):
        """Set configuration value by dot-separated path"""
        keys = key_path.split('.')
        config = self._config

        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]

        config[keys[-1]] = value

    def get_api_key(self, provider: str) -> str:
        """Get API key for a specific provider"""
        key = self.get(f'api_keys.{provider}')
        if not key:
            raise ValueError(
                f"API key for '{provider}' not found. "
                f"Please set it in config.yaml or as environment variable."
            )
        return key

    def ensure_directories(self):
        """Create necessary directories if they don't exist"""
        paths_config = self.get('paths', {})

        for path_key, path_value in paths_config.items():
            path = Path(path_value)
            path.mkdir(parents=True, exist_ok=True)

        # Also create logs directory
        Path("logs").mkdir(exist_ok=True)

    @property
    def image_generation_settings(self) -> Dict:
        """Get image generation settings"""
        return self.get('default_settings.image_generation', {})

    @property
    def generation_settings(self) -> Dict:
        """Get 3D generation settings"""
        return self.get('default_settings.generation', {})

    @property
    def postprocessing_settings(self) -> Dict:
        """Get post-processing settings"""
        return self.get('default_settings.postprocessing', {})

    @property
    def printer_settings(self) -> Dict:
        """Get printer settings"""
        return self.get('default_settings.printer', {})

    @property
    def mcp_settings(self) -> Dict:
        """Get MCP server settings"""
        return self.get('mcp', {})

    def __repr__(self):
        return f"Config(config_path='{self.config_path}')"


# Global config instance
_config_instance = None


def load_config(config_path: str = "config.yaml") -> Config:
    """Load or get the global configuration instance"""
    global _config_instance

    if _config_instance is None:
        _config_instance = Config(config_path)
        _config_instance.ensure_directories()

    return _config_instance


def get_config() -> Config:
    """Get the current configuration instance"""
    if _config_instance is None:
        return load_config()
    return _config_instance
