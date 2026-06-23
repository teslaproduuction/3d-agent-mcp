"""
Miscellaneous handlers: chat and model selection.
"""
from typing import List
from utils.logger import get_logger

logger = get_logger(__name__)


class MiscHandlersMixin:

    async def handle_chat_message(self, message: str, history: List, session_id: str | None = None):
        """Handle chat message from user."""
        self.set_active_session(session_id)

        if not history:
            history = list(self.conversation_history)

        if not message.strip():
            return "", history

        history.append({"role": "user", "content": message})
        try:
            response = await self.coordinator.process_chat_message(message)
            history.append({"role": "assistant", "content": response})
        except Exception as e:
            logger.error(f"Chat error: {e}")
            history.append({"role": "assistant", "content": f"Error: {str(e)}"})

        self.conversation_history = history
        return "", history

    def on_model_select(self, session_id: str, selected_index):
        """Handle model selection from dropdown — update viewer + analysis."""
        from ui.helpers import format_analysis
        from ui.helpers import get_printable_compare_payload

        self.set_active_session(session_id)

        if selected_index is None or not self.generated_models:
            self.selected_model_index = None
            return (
                None,
                "*Модель не выбрана*",
                "",
                {},
                None,
                None,
                None,
                "*Сравнение до/после пока недоступно*",
            )

        if isinstance(selected_index, str):
            try:
                selected_index = int(selected_index)
            except (ValueError, TypeError):
                for i, model in enumerate(self.generated_models):
                    if model.get('object_name') == selected_index:
                        selected_index = i
                        break
                else:
                    self.selected_model_index = None
                    return (
                        None,
                        "*Модель не найдена*",
                        "",
                        {},
                        None,
                        None,
                        None,
                        "*Сравнение до/после пока недоступно*",
                    )

        if selected_index >= len(self.generated_models):
            self.selected_model_index = None
            return (
                None,
                "*Неверный индекс*",
                "",
                {},
                None,
                None,
                None,
                "*Сравнение до/после пока недоступно*",
            )

        result = self.generated_models[selected_index]
        self.selected_model_index = selected_index
        compare_before, compare_after, compare_heatmap, compare_info = get_printable_compare_payload(result)
        return (
            result.get('model_file'),
            format_analysis(result.get('analysis')),
            result.get('reasoning', ''),
            result.get('metadata', {}),
            compare_before,
            compare_after,
            compare_heatmap,
            compare_info,
        )
