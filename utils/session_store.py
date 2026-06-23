"""
Redis-backed session store for persisting UI state across reloads and restarts.
Falls back to in-memory storage if Redis is unavailable.
"""
import copy
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

REDIS_KEY_PREFIX = "3dagent:session"
DEFAULT_SESSION_TTL_SECONDS = 24 * 60 * 60

DEFAULT_STATE: dict = {
    "preview_candidates": [],
    "generated_models": [],
    "multiview_images": [],
    "current_image_prompt": "",
    "conversation_history": [],
    "selected_image_index": None,
    "selected_multiview_index": "0",
    "selected_model_index": None,
    "ui_settings": {},
}


def _clone_default_state() -> dict:
    return copy.deepcopy(DEFAULT_STATE)


class SessionStore:
    """
    Persists session state in Redis so that page reloads and app restarts
    do not lose preview candidates, generated models, or multiview images.
    Falls back to an in-memory dict if Redis is not reachable.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    ):
        self._redis = None
        self._memory_by_session: dict[str, dict] = {}
        self._use_redis = False
        self._session_ttl_seconds = max(60, int(session_ttl_seconds or DEFAULT_SESSION_TTL_SECONDS))

        try:
            import redis as redis_lib
            client = redis_lib.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
                retry_on_timeout=True,
            )
            client.ping()
            self._redis = client
            self._use_redis = True
            logger.info(f"Session store connected to Redis: {redis_url}")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}), session state will not persist across restarts")

    @property
    def using_redis(self) -> bool:
        return self._use_redis

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize_session_id(self, session_id: str | None) -> str:
        if session_id is None:
            return "default"

        raw = str(session_id).strip()
        if not raw:
            return "default"

        allowed = "-_."
        cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in allowed)
        return cleaned[:128] or "default"

    def _redis_key(self, session_id: str) -> str:
        return f"{REDIS_KEY_PREFIX}:{session_id}"

    def _load_session(self, session_id: str) -> dict:
        state = _clone_default_state()

        if not self._use_redis:
            self._memory_by_session[session_id] = state
            return state

        try:
            raw = self._redis.get(self._redis_key(session_id))
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    for key in DEFAULT_STATE:
                        if key in data:
                            state[key] = data[key]
                    logger.info(f"Session state restored from Redis for session_id={session_id}")
            self._touch_ttl(session_id)
        except Exception as e:
            logger.error(f"Failed to load session from Redis for session_id={session_id}: {e}")

        self._memory_by_session[session_id] = state
        return state

    def _touch_ttl(self, session_id: str):
        if not self._use_redis:
            return

        try:
            self._redis.expire(self._redis_key(session_id), self._session_ttl_seconds)
        except Exception as e:
            logger.error(f"Failed to refresh session TTL for session_id={session_id}: {e}")

    def _get_session_memory(self, session_id: str | None) -> tuple[str, dict]:
        normalized = self._normalize_session_id(session_id)
        if normalized not in self._memory_by_session:
            return normalized, self._load_session(normalized)

        self._touch_ttl(normalized)
        return normalized, self._memory_by_session[normalized]

    def _save_session(self, session_id: str, state: dict):
        """Persist current session memory to Redis."""
        if not self._use_redis:
            return

        try:
            self._redis.set(
                self._redis_key(session_id),
                json.dumps(state, ensure_ascii=False),
                ex=self._session_ttl_seconds,
            )
        except Exception as e:
            logger.error(f"Failed to save session to Redis for session_id={session_id}: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_session(self, session_id: str | None):
        """Ensure session state is loaded for this session_id."""
        self._get_session_memory(session_id)

    def normalize_session_id(self, session_id: str | None) -> str:
        return self._normalize_session_id(session_id)

    def get(self, key: str, default: Any = None, session_id: str | None = None) -> Any:
        _, state = self._get_session_memory(session_id)
        fallback = default if default is not None else DEFAULT_STATE.get(key)
        value = state.get(key, fallback)
        if isinstance(value, (dict, list)):
            return copy.deepcopy(value)
        return value

    def set(self, key: str, value: Any, session_id: str | None = None):
        normalized, state = self._get_session_memory(session_id)
        state[key] = value
        self._save_session(normalized, state)

    def reset(self, session_id: str | None = None):
        """Clear all session state (useful for 'New session' button)."""
        normalized = self._normalize_session_id(session_id)
        state = _clone_default_state()
        self._memory_by_session[normalized] = state
        self._save_session(normalized, state)
        logger.info(f"Session state reset for session_id={normalized}")
