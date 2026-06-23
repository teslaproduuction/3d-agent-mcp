"""
AppState mixin — Redis-backed session state properties.
Included in GradioInterface via multiple inheritance.
"""
import contextvars
import os
from utils.logger import get_logger

logger = get_logger(__name__)


DEFAULT_UI_SETTINGS = {
    "image_provider": "local",
    "llm_provider": "ollama",
    "llm_model": "qwen2.5:32b",
    "generation_mode": "Локальная модель",
    "api_provider": "tripo",
    "local_model": None,
    "use_multiview": True,
    "enable_intelligent_processing": True,
    "auto_orient": True,
    "generate_supports": True,
    "max_overhang_angle": 45,
    "make_overhangs_printable": False,
    "overhang_printable_angle": 55.0,
    "overhang_printable_holes": 0.0,
    "bg_removal_mode": "Прозрачный фон",
}


class AppState:
    """Mixin that adds persisted state properties backed by Redis (SessionStore)."""

    def _init_state(self):
        from utils.session_store import SessionStore

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        ttl_raw = os.getenv("REDIS_SESSION_TTL_SECONDS", "86400")
        try:
            session_ttl_seconds = int(ttl_raw)
        except (TypeError, ValueError):
            session_ttl_seconds = 86400

        self._session_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
            "active_session_id",
            default="default",
        )
        self._store = SessionStore(redis_url, session_ttl_seconds=session_ttl_seconds)

        if self._store.using_redis:
            logger.info(f"Session state will persist in Redis across restarts (ttl={session_ttl_seconds}s)")
        else:
            logger.warning("Running without Redis — session state is in-memory only")

    # ------------------------------------------------------------------
    # Session context helpers
    # ------------------------------------------------------------------

    def set_active_session(self, session_id: str | None) -> str:
        normalized = self._store.normalize_session_id(session_id)
        self._store.ensure_session(normalized)
        self._session_ctx.set(normalized)
        return normalized

    def _active_session_id(self) -> str:
        return self._session_ctx.get()

    def _state_get(self, key: str, default=None):
        return self._store.get(key, default, session_id=self._active_session_id())

    def _state_set(self, key: str, value):
        self._store.set(key, value, session_id=self._active_session_id())

    # ------------------------------------------------------------------
    # Persisted workflow state
    # ------------------------------------------------------------------

    @property
    def preview_candidates(self) -> list:
        return self._state_get('preview_candidates', [])

    @preview_candidates.setter
    def preview_candidates(self, value: list):
        self._state_set('preview_candidates', value)

    @property
    def generated_models(self) -> list:
        return self._state_get('generated_models', [])

    @generated_models.setter
    def generated_models(self, value: list):
        self._state_set('generated_models', value)

    @property
    def multiview_images(self) -> list:
        return self._state_get('multiview_images', [])

    @multiview_images.setter
    def multiview_images(self, value: list):
        self._state_set('multiview_images', value)

    @property
    def current_image_prompt(self) -> str:
        return self._state_get('current_image_prompt', '')

    @current_image_prompt.setter
    def current_image_prompt(self, value: str):
        self._state_set('current_image_prompt', value)

    @property
    def conversation_history(self) -> list:
        return self._state_get('conversation_history', [])

    @conversation_history.setter
    def conversation_history(self, value: list):
        self._state_set('conversation_history', value)

    @property
    def selected_image_index(self):
        return self._state_get('selected_image_index', None)

    @selected_image_index.setter
    def selected_image_index(self, value):
        self._state_set('selected_image_index', value)

    @property
    def selected_multiview_index(self):
        return self._state_get('selected_multiview_index', '0')

    @selected_multiview_index.setter
    def selected_multiview_index(self, value):
        self._state_set('selected_multiview_index', value)

    @property
    def selected_model_index(self):
        return self._state_get('selected_model_index', None)

    @selected_model_index.setter
    def selected_model_index(self, value):
        self._state_set('selected_model_index', value)

    @property
    def ui_settings(self) -> dict:
        saved = self._state_get('ui_settings', {}) or {}
        merged = dict(DEFAULT_UI_SETTINGS)
        merged.update(saved)
        return merged

    @ui_settings.setter
    def ui_settings(self, value: dict):
        merged = dict(DEFAULT_UI_SETTINGS)
        merged.update(value or {})
        self._state_set('ui_settings', merged)

    def get_ui_setting(self, key: str, default=None):
        settings = self.ui_settings
        if default is None:
            return settings.get(key, DEFAULT_UI_SETTINGS.get(key))
        return settings.get(key, default)

    def update_ui_setting(self, key: str, value):
        settings = self.ui_settings
        settings[key] = value
        self.ui_settings = settings
