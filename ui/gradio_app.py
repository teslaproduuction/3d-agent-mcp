"""
GradioInterface — thin orchestrator that assembles UI from modular components.

Structure
---------
ui/
├── gradio_app.py        ← you are here (class + launch)
├── state.py             ← Redis-backed state properties (AppState mixin)
├── helpers.py           ← utilities: create_llm_client, format_analysis, …
├── events.py            ← all .click()/.change() wiring (wire_events)
├── tabs/
│   ├── left_panel.py    ← input column (description → prompt → settings)
│   ├── preview_tab.py   ← Tab 1: preview gallery + bg removal
│   ├── multiview_tab.py ← Tab 2: multi-view gallery + per-view regen
│   ├── model_tab.py     ← Tab 3: 3D viewer + analysis
│   └── printable_tab.py ← Tab 4: printable gallery + download
└── handlers/
    ├── image.py         ← handle_generate_prompt/images/remove_background
    ├── generation.py    ← handle_generate_3d, handle_continue_to_3d, generate_scene
    ├── multiview.py     ← handle_regenerate_multiview
    └── misc.py          ← handle_chat_message, on_model_select
"""
import os

import gradio as gr

from utils.config import load_config
from utils.logger import get_logger

from ui.state import AppState
from ui.helpers import get_local_models_from_config
from ui.handlers.image import ImageHandlersMixin
from ui.handlers.generation import GenerationHandlersMixin
from ui.handlers.multiview import MultiviewHandlersMixin
from ui.handlers.misc import MiscHandlersMixin
from ui.handlers.orientation import OrientationHandlersMixin
from ui.handlers.monitoring import MonitoringMixin
from ui.handlers.analytics import AnalyticsMixin
from ui.tabs.left_panel import build_left_panel
from ui.tabs.preview_tab import build_preview_tab
from ui.tabs.multiview_tab import build_multiview_tab
from ui.tabs.model_tab import build_model_tab
from ui.tabs.printable_tab import build_printable_tab
from ui.tabs.monitoring_tab import build_monitoring_tab
from ui.tabs.analytics_tab import build_analytics_tab
from ui.events import wire_events

logger = get_logger(__name__)


SESSION_INIT_JS = """
() => {
    // Single shared session mode: disable per-tab/per-browser session IDs.
    return ["default"];
}
"""


class GradioInterface(
    AppState,
    ImageHandlersMixin,
    GenerationHandlersMixin,
    MultiviewHandlersMixin,
    MiscHandlersMixin,
    OrientationHandlersMixin,
    MonitoringMixin,
    AnalyticsMixin,
):
    """Gradio web interface for the 3D generation system."""

    def __init__(self, coordinator=None):
        self.config = load_config()

        if coordinator is None:
            logger.info("No coordinator provided, creating legacy CoordinatorAgent")
            from agents.coordinator import CoordinatorAgent
            self.coordinator = CoordinatorAgent(self.config)
        else:
            logger.info(f"Using provided coordinator: {type(coordinator).__name__}")
            self.coordinator = coordinator

        self._init_state()  # from AppState — sets up self._store (Redis)
        self.local_models = get_local_models_from_config(self.config)

        # Warm up background-removal model early to avoid first-click latency.
        warmup_enabled = os.getenv("REMBG_WARMUP_ON_START", "1").strip().lower() not in {"0", "false", "no"}
        if warmup_enabled:
            try:
                from utils.image_processor import warmup_rembg_session
                elapsed = warmup_rembg_session()
                logger.info(f"Warmup удаления фона завершен за {elapsed:.2f}с")
            except Exception as e:
                logger.warning(f"Не удалось прогреть модель удаления фона: {e}")

        self.set_active_session("default")
        self.current_scene_plan = []
        self.generated_previews = []

    # ------------------------------------------------------------------

    @staticmethod
    def _existing_file(path):
        return isinstance(path, str) and os.path.exists(path)

    @staticmethod
    def _to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _llm_presets(provider: str):
        presets = {
            "openai": {
                "choices": ["gpt-4o-mini", "gpt-4o", "o1-mini", "o3-mini"],
                "value": "gpt-4o-mini",
            },
            "anthropic": {
                "choices": ["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5-20251001"],
                "value": "claude-sonnet-4-6",
            },
            "google": {
                "choices": ["gemini-2.0-flash", "gemini-2.0-pro", "gemini-1.5-pro"],
                "value": "gemini-2.0-flash",
            },
            "ollama": {
                "choices": ["qwen2.5:7b", "qwen2.5:3b", "qwen2.5:1.5b", "llama3.2:1b"],
                "value": "qwen2.5:7b",
            },
        }
        return presets.get(provider, presets["openai"])

    def persist_ui_setting(self, session_id: str, setting_key: str, setting_value):
        self.set_active_session(session_id)
        self.update_ui_setting(setting_key, setting_value)

    def persist_selected_image_index(self, session_id: str, selected_index):
        self.set_active_session(session_id)
        self.selected_image_index = selected_index

    def persist_selected_multiview_index(self, session_id: str, selected_index):
        self.set_active_session(session_id)
        self.selected_multiview_index = selected_index

    def _sanitize_session_state(self):
        preview_candidates = self.preview_candidates
        valid_preview_candidates = []
        preview_paths = []

        for candidate in preview_candidates:
            if not isinstance(candidate, dict):
                continue

            image_path = candidate.get("image_path")
            if self._existing_file(image_path):
                valid_preview_candidates.append(candidate)
                preview_paths.append(image_path)

        if len(valid_preview_candidates) != len(preview_candidates):
            self.preview_candidates = valid_preview_candidates

        multiview_paths = [p for p in self.multiview_images if self._existing_file(p)]
        if len(multiview_paths) != len(self.multiview_images):
            self.multiview_images = multiview_paths

        models = []
        for model in self.generated_models:
            if not isinstance(model, dict):
                continue

            model_file = model.get("model_file")
            if self._existing_file(model_file):
                models.append(model)

        if len(models) != len(self.generated_models):
            self.generated_models = models

        return preview_paths, multiview_paths, models

    def handle_session_load(self, session_id: str):
        from ui.helpers import format_analysis, get_printable_compare_payload

        self.set_active_session(session_id)
        preview_paths, multiview_paths, models = self._sanitize_session_state()

        selected_image_raw = self.selected_image_index
        selected_image_idx = self._to_int(selected_image_raw)
        selected_image_value = None
        if selected_image_idx is not None and 0 <= selected_image_idx < len(preview_paths):
            selected_image_value = str(selected_image_idx)
        self.selected_image_index = selected_image_value

        selected_multiview_raw = self.selected_multiview_index
        selected_multiview_idx = self._to_int(selected_multiview_raw)
        if selected_multiview_idx is None or not (0 <= selected_multiview_idx <= 3):
            selected_multiview_value = "0"
        else:
            selected_multiview_value = str(selected_multiview_idx)
        self.selected_multiview_index = selected_multiview_value

        selected_model_raw = self.selected_model_index
        selected_model_idx = self._to_int(selected_model_raw)
        if selected_model_idx is None or not (0 <= selected_model_idx < len(models)):
            selected_model_idx = 0 if models else None
        self.selected_model_index = selected_model_idx

        model_choices = []
        selected_model_value = None
        model_viewer_value = None
        analysis_value = "*Анализ пока недоступен*"
        reasoning_value = ""
        metadata_value = {}
        printable_before_value = None
        printable_after_value = None
        printable_heatmap_value = None
        printable_compare_info = "*Сравнение до/после пока недоступно*"

        if models:
            for i, model in enumerate(models):
                model_choices.append((model.get("object_name", f"model_{i}"), i))

            selected_model_value = selected_model_idx if selected_model_idx is not None else 0
            selected_model = models[selected_model_value]
            model_viewer_value = selected_model.get("model_file")
            analysis_value = format_analysis(selected_model.get("analysis"))
            reasoning_value = selected_model.get("reasoning", "")
            metadata_value = selected_model.get("metadata", {})
            (
                printable_before_value,
                printable_after_value,
                printable_heatmap_value,
                printable_compare_info,
            ) = get_printable_compare_payload(selected_model)

        settings = self.ui_settings
        llm_provider_value = settings.get("llm_provider", "ollama")
        if llm_provider_value not in {"openai", "anthropic", "google", "ollama"}:
            llm_provider_value = "ollama"

        llm_preset = self._llm_presets(llm_provider_value)
        llm_model_value = settings.get("llm_model") or llm_preset["value"]

        # Recover from corrupted/legacy values where provider name was stored as model.
        if llm_model_value in {"openai", "anthropic", "google", "ollama"}:
            llm_model_value = llm_preset["value"]

        llm_choices = list(llm_preset["choices"])
        if llm_model_value not in llm_choices:
            llm_model_value = llm_preset["value"]

        local_model_value = settings.get("local_model")
        if local_model_value is None and self.local_models:
            local_model_value = self.local_models[0].get("name")

        generation_mode_value = settings.get("generation_mode", "Локальная модель")
        api_provider_visible = generation_mode_value == "API (Cloud)"
        local_model_visible = generation_mode_value == "Локальная модель"
        make_overhangs_printable_value = bool(settings.get("make_overhangs_printable", False))

        has_state = bool(
            self.current_image_prompt
            or preview_paths
            or multiview_paths
            or models
            or self.conversation_history
        )
        status_message = (
            "Сессия восстановлена"
            if has_state
            else "Новая сессия инициализирована"
        )

        return (
            self.current_image_prompt,
            preview_paths,
            multiview_paths,
            model_viewer_value,
            gr.update(choices=model_choices, value=selected_model_value),
            analysis_value,
            reasoning_value,
            metadata_value,
            printable_before_value,
            printable_after_value,
            printable_heatmap_value,
            printable_compare_info,
            selected_image_value,
            selected_multiview_value,
            settings.get("image_provider", "local"),
            llm_provider_value,
            gr.update(choices=llm_choices, value=llm_model_value),
            generation_mode_value,
            gr.update(value=settings.get("api_provider", "tripo"), visible=api_provider_visible),
            gr.update(value=local_model_value, visible=local_model_visible),
            bool(settings.get("use_multiview", True)),
            bool(settings.get("enable_intelligent_processing", True)),
            bool(settings.get("auto_orient", True)),
            bool(settings.get("generate_supports", True)),
            settings.get("max_overhang_angle", 45),
            make_overhangs_printable_value,
            gr.update(
                value=settings.get("overhang_printable_angle", 55.0),
                visible=make_overhangs_printable_value,
            ),
            gr.update(
                value=settings.get("overhang_printable_holes", 0.0),
                visible=make_overhangs_printable_value,
            ),
            settings.get("bg_removal_mode", "Прозрачный фон"),
            status_message,
        )

    # ------------------------------------------------------------------

    def build_interface(self):
        """Assemble the full Gradio Blocks interface."""
        with gr.Blocks(title="Система автоматизированной генерации 3D-моделей") as demo:
            # Single-session mode: keep a fixed session id and skip load-time hydration.
            session_id = gr.Textbox(value="default", visible=False, elem_id="session_id")

            gr.Markdown("""
            # Система автоматизированной генерации 3D-моделей

            Создавайте 3D модели с помощью ИИ и интеллектуальной постобработки
            """)

            with gr.Row():
                left = build_left_panel(self.local_models, self.config)

                with gr.Column(scale=2):
                    with gr.Tabs():
                        preview    = build_preview_tab()
                        mview      = build_multiview_tab()
                        model      = build_model_tab()
                        printable  = build_printable_tab()
                        monitoring = build_monitoring_tab()
                        analytics  = build_analytics_tab()

            components = {**left, **preview, **mview, **model, **printable, **monitoring, **analytics, "session_id": session_id}
            wire_events(self, components)

        return demo

    def launch(self, **kwargs):
        """Build and launch the Gradio interface."""
        demo = self.build_interface()

        queue_enabled = os.getenv("GRADIO_ENABLE_QUEUE", "1").strip().lower() not in {"0", "false", "no"}
        if queue_enabled:
            try:
                queue_limit = int(os.getenv("GRADIO_QUEUE_CONCURRENCY", "1"))
            except (TypeError, ValueError):
                queue_limit = 1
            try:
                queue_max_size = int(os.getenv("GRADIO_QUEUE_MAX_SIZE", "32"))
            except (TypeError, ValueError):
                queue_max_size = 32

            demo.queue(
                status_update_rate=1,
                max_size=max(1, queue_max_size),
                default_concurrency_limit=max(1, queue_limit),
            )

        demo.launch(**kwargs)


# Async handlers are used natively by Gradio.
