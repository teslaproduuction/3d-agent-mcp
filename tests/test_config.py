"""
Tests for configuration management
"""
import pytest
from pathlib import Path
from utils.config import Config


def test_config_loading():
    """Test loading configuration from YAML"""
    config = Config('config.yaml')
    assert config is not None
    assert isinstance(config._config, dict)


def test_config_get_nested():
    """Test getting nested configuration values"""
    config = Config('config.yaml')

    # Test nested path
    provider = config.get('default_settings.generation.api_provider')
    assert provider in ['tripo', 'meshy', 'local', None]

    # Test with default
    value = config.get('nonexistent.path', default='default_value')
    assert value == 'default_value'


def test_config_properties():
    """Test configuration properties"""
    config = Config('config.yaml')

    assert isinstance(config.image_generation_settings, dict)
    assert isinstance(config.generation_settings, dict)
    assert isinstance(config.postprocessing_settings, dict)
    assert isinstance(config.printer_settings, dict)


def test_ensure_directories():
    """Test directory creation"""
    config = Config('config.yaml')
    config.ensure_directories()

    # Check that output directories exist
    assert Path('outputs').exists()
    assert Path('outputs/flux').exists()
    assert Path('outputs/previews').exists()
    assert Path('logs').exists()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
