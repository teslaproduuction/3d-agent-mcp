"""
Standalone helper utilities shared across the UI layer.
"""
import asyncio
import os
from typing import Dict, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def get_local_models_from_config(config) -> list:
    """Return list of available local 3D models from config."""
    models_config = config.get('default_settings.local_3d_models', {})

    if not models_config.get('enabled', False):
        logger.info("Local 3D models disabled in config")
        return []

    available_models = models_config.get('available_models', [])
    if not available_models:
        logger.warning("No local models configured, using defaults")
        return [
            {"name": "triposr",   "display_name": "TripoSR (быстро)"},
            {"name": "shap-e",    "display_name": "Shap-E (качество)"},
            {"name": "instant3d", "display_name": "Instant3D (балансированно)"},
        ]

    logger.info(f"Loaded {len(available_models)} local models from config")
    return available_models


# ---------------------------------------------------------------------------
# LLM client factory
# ---------------------------------------------------------------------------

def create_llm_client(provider: str, model: str, coordinator):
    """
    Create an LLMClient for the given provider/model.
    Falls back to coordinator.llm_client for unknown providers.
    """
    import os
    from api_clients.llm_client import LLMClient

    logger.info(f"Creating LLM client: {provider}/{model}")

    if provider == "openai":
        return LLMClient(provider="openai", api_key=os.getenv("OPENAI_API_KEY"), model=model)

    if provider == "anthropic":
        return LLMClient(provider="anthropic", api_key=os.getenv("ANTHROPIC_API_KEY"), model=model)

    if provider == "google":
        logger.warning("Google provider not yet implemented, falling back to coordinator LLM client")
        return coordinator.llm_client

    if provider == "ollama":
        from utils.config import get_config
        ollama_url = get_config().get('llm.local.ollama_base_url', 'http://localhost:11434/v1')
        return LLMClient(provider="openai", api_key="ollama", model=model, base_url=ollama_url)

    logger.warning(f"Unknown provider '{provider}', falling back to coordinator LLM client")
    return coordinator.llm_client


# ---------------------------------------------------------------------------
# Analysis formatter
# ---------------------------------------------------------------------------

def format_analysis(analysis: Optional[Dict]) -> str:
    """Format analysis dict as markdown string."""
    if not analysis:
        return "*Анализ недоступен*"

    md = "### Анализ печатаемости\n\n"
    md += f"**Сложность:** {analysis.get('complexity', 'Неизвестно').upper()}\n\n"
    md += f"**Сложность печати:** {analysis.get('print_difficulty', 'Неизвестно').upper()}\n\n"

    md += "#### Геометрия:\n"
    md += f"- Макс. свес: {analysis.get('max_overhang_angle', 0):.1f}°\n"
    md += f"- Площадь свеса: {analysis.get('overhang_area_mm2', 0):.1f} мм²\n"
    md += f"- Площадь контакта: {analysis.get('contact_area_mm2', 0):.1f} мм²\n"
    md += f"- Внутренние полости: {'Да ⚠️' if analysis.get('has_internal_cavities') else 'Нет ✓'}\n\n"

    md += "#### Рекомендации:\n"
    md += f"- Печать без поддержек: {'Да ✓' if analysis.get('is_printable_without_supports') else 'Нет ✗'}\n"
    md += f"- Рекомендованная стратегия поддержек: **{analysis.get('recommended_support_strategy', 'нет').upper()}**\n"

    return md


def get_printable_compare_payload(model_result: Optional[Dict]) -> tuple:
    """Extract before/after/heatmap model paths and formatted stats markdown."""
    if not model_result:
        return None, None, None, "*Сравнение до/после пока недоступно*"

    comparison = model_result.get('comparison') if isinstance(model_result, dict) else None
    if not isinstance(comparison, dict):
        comparison = {}

    before_model = comparison.get('before_model_file') or model_result.get('source_model_file')
    after_model = comparison.get('after_model_file') or model_result.get('model_file')
    heatmap_model = comparison.get('heatmap_model_file')
    stats = comparison.get('heatmap_stats', {}) or {}

    if before_model and not os.path.exists(before_model):
        before_model = None
    if after_model and not os.path.exists(after_model):
        after_model = None
    if heatmap_model and not os.path.exists(heatmap_model):
        heatmap_model = None

    if not after_model:
        return None, None, None, "*Сравнение до/после пока недоступно*"

    if stats:
        md = "### Тепловая карта изменений\n\n"
        md += f"- Среднее изменение: {stats.get('mean_mm', 0.0):.3f} мм\n"
        md += f"- 95-й перцентиль: {stats.get('p95_mm', 0.0):.3f} мм\n"
        md += f"- Максимум: {stats.get('max_mm', 0.0):.3f} мм\n"
        if 'color_scale_max_mm' in stats:
            md += f"- Верхняя граница цвета: {stats.get('color_scale_max_mm', 0.0):.3f} мм\n"
        if 'icp_cost' in stats:
            md += f"- Ошибка выравнивания (ICP): {stats.get('icp_cost', 0.0):.6f}\n"
        if 'alignment_method' in stats:
            md += f"- Метод выравнивания: {stats.get('alignment_method')}\n"
        if 'alignment_scale' in stats:
            md += f"- Масштаб выравнивания: {stats.get('alignment_scale', 1.0):.4f}\n"
        md += "\nЦвет: синий → низкое изменение, красный → сильное изменение."
    elif before_model and before_model != after_model:
        md = "### Сравнение до/после\n\nТепловая карта не была построена для этой модели."
    else:
        md = "### Сравнение до/после\n\nИзменений геометрии после обработки не обнаружено."

    return before_model, after_model, heatmap_model, md


# ---------------------------------------------------------------------------
# Async → sync wrapper (for Gradio event handlers)
# ---------------------------------------------------------------------------

def create_async_wrapper(async_fn):
    """Wrap an async method so Gradio can call it synchronously."""
    def wrapper(self, *args, **kwargs):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(async_fn(self, *args, **kwargs))
    return wrapper
