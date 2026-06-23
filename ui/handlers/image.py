"""
Image generation and background-removal handlers.
"""
import asyncio
import random
import time

import gradio as gr
from utils.logger import get_logger

logger = get_logger(__name__)

_RANDOM_IDEA_SYSTEM = "Ты генератор идей. Отвечай ТОЛЬКО на русском языке. Никакого китайского, английского или других языков."

_RANDOM_IDEA_PROMPT = """\
Придумай одну идею для 3D-печати фигурки. Подсказка категории: {hint}.

Примеры хороших ответов:
- Сидящий кот с книгой в лапах
- Дракон свернувшийся клубком со смешным выражением
- Лиса в шляпе с метлой
- Пингвин в шарфе со снежком в крыле
- Медведь играющий на виолончели

Ответь одной фразой на русском языке (5-12 слов). Только описание, без пояснений."""


class ImageHandlersMixin:

    async def handle_random_idea(self, session_id: str, llm_provider: str, llm_model: str):
        """Generate a random 3D-printable figurine idea using LLM."""
        self.set_active_session(session_id)
        try:
            from ui.helpers import create_llm_client
            llm_client = create_llm_client(llm_provider, llm_model, self.coordinator)

            original = self.coordinator.llm_client
            self.coordinator.llm_client = llm_client
            try:
                # Add a random seed hint so the LLM varies its output
                seed_hint = random.choice([
                    "животное", "фэнтези существо", "милый персонаж",
                    "морское существо", "лесное животное", "птица", "рептилия",
                    "мифическое существо", "домашний питомец", "хищник",
                ])
                response = await llm_client.complete(
                    prompt=_RANDOM_IDEA_PROMPT.format(hint=seed_hint),
                    system_prompt=_RANDOM_IDEA_SYSTEM,
                    max_tokens=60,
                    temperature=0.9,
                )
                import re
                idea = response.strip().strip('"\'«»').strip()
                # Remove underscore-artifacts like _story_fix_, _ответ_ etc.
                idea = re.sub(r'_\w+_', '', idea).strip()
                # Remove standalone English words (keep Cyrillic, digits, punctuation, spaces)
                idea = re.sub(r'\b[a-zA-Z]{3,}\b', '', idea).strip()
                # Collapse multiple spaces/commas left after cleanup
                idea = re.sub(r'\s{2,}', ' ', idea).strip().strip(',').strip()
                # Reject Chinese or empty result
                if re.search(r'[\u4e00-\u9fff\u3000-\u303f]', idea) or len(idea) < 5:
                    raise ValueError(f"Bad response: {idea}")
                logger.info(f"Random idea generated: {idea}")
                return idea, f"Идея: {idea}"
            finally:
                self.coordinator.llm_client = original

        except Exception as e:
            logger.error(f"Random idea error: {e}")
            # Fallback: return a random idea from a fixed list
            fallback = random.choice([
                "Сидящий кот с книгой в лапах",
                "Дракон свернувшийся клубком",
                "Лиса в шляпе волшебника",
                "Медведь играющий на гитаре",
                "Кролик астронавт в скафандре",
                "Сова с очками на ветке",
                "Черепаха с домиком-замком",
                "Пингвин в шарфе со снежком",
            ])
            return fallback, f"Случайная идея (оффлайн): {fallback}"

    async def handle_generate_prompt(self, session_id: str, user_description: str, llm_provider: str, llm_model: str):
        """Generate optimized image prompt from user description."""
        self.set_active_session(session_id)
        self.update_ui_setting('llm_provider', llm_provider)
        self.update_ui_setting('llm_model', llm_model)

        if not user_description.strip():
            return "", "⚠️ Введите описание объекта"

        try:
            logger.info(f"Generating prompt for: {user_description} (LLM: {llm_provider}/{llm_model})")

            from ui.helpers import create_llm_client
            llm_client = create_llm_client(llm_provider, llm_model, self.coordinator)

            original = self.coordinator.llm_client
            self.coordinator.llm_client = llm_client
            _t0 = time.perf_counter()
            try:
                optimized_prompt = await self.coordinator.generate_image_prompt(user_description)
                _elapsed = time.perf_counter() - _t0
                self.current_image_prompt = optimized_prompt
                # Store LLM prompt time for metrics (picked up by handle_generate_3d)
                self.update_ui_setting('_metric_time_llm_prompt', _elapsed)
                return optimized_prompt, f"✅ Промпт сгенерирован ({llm_provider}/{llm_model}) за {_elapsed:.1f}с"
            finally:
                self.coordinator.llm_client = original

        except Exception as e:
            logger.error(f"Prompt generation error: {e}")
            return "", f"❌ Ошибка: {str(e)}"

    async def handle_generate_images(self, session_id: str, image_prompt: str, image_provider: str):
        """Generate 4 preview candidate images."""
        self.set_active_session(session_id)
        self.update_ui_setting('image_provider', image_provider)

        if not image_prompt.strip():
            return [], "⚠️ Введите промпт для изображений"

        try:
            logger.info(f"Generating 4 preview candidates with provider: {image_provider}")
            self.current_image_prompt = image_prompt
            self.update_ui_setting('image_prompt', image_prompt)

            _t0 = time.perf_counter()
            candidates = await self.coordinator.generate_preview_candidates(
                prompt=image_prompt,
                num_candidates=4,
                style="realistic 3D render, product design"
            )
            _elapsed = time.perf_counter() - _t0

            image_paths = [
                c['image_path'] for c in candidates
                if 'error' not in c and 'image_path' in c
            ]

            self.preview_candidates = candidates
            self.multiview_images = []  # Reset stale multiview from previous generation
            self.selected_image_index = None
            self.selected_multiview_index = "0"
            self.selected_model_index = None

            # Store image generation time for metrics (picked up by handle_generate_3d)
            self.update_ui_setting('_metric_time_image_gen', _elapsed)

            if not image_paths:
                return [], "❌ Не удалось сгенерировать изображения"

            return image_paths, f"✅ Сгенерировано {len(image_paths)} превью за {_elapsed:.1f}с! Выберите понравившееся и нажмите 'Генерировать 3D'"

        except Exception as e:
            logger.error(f"Image generation error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return [], f"❌ Ошибка: {str(e)}"

    async def handle_remove_background(self, session_id: str, selected_image_index: str, bg_removal_mode: str):
        """Remove / replace background of the selected preview image."""
        self.set_active_session(session_id)
        self.update_ui_setting('bg_removal_mode', bg_removal_mode)

        if selected_image_index is None:
            return gr.update(), "⚠️ Выберите изображение", "⚠️ Сначала выберите изображение для удаления фона"

        try:
            idx = int(selected_image_index)
            if idx >= len(self.preview_candidates):
                return gr.update(), "❌ Неверный индекс", "❌ Неверный индекс изображения"

            selected_candidate = self.preview_candidates[idx]
            if 'error' in selected_candidate:
                return gr.update(), "❌ Изображение содержит ошибку", "❌ Выбранное изображение содержит ошибку"

            selected_image_path = selected_candidate['image_path']
            logger.info(f"Removing background from image {idx}: {selected_image_path}")

            from utils.image_processor import ImageProcessor
            started_at = time.perf_counter()

            if bg_removal_mode == "Белый фон":
                output_path = await asyncio.to_thread(
                    ImageProcessor.create_white_background,
                    selected_image_path,
                )
            else:
                output_path = await asyncio.to_thread(
                    ImageProcessor.remove_background,
                    selected_image_path,
                )

            elapsed = time.perf_counter() - started_at

            logger.info(f"Background removed in {elapsed:.2f}s: {output_path}")

            # Read-modify-write for Redis
            candidates = self.preview_candidates
            candidates[idx]['image_path'] = output_path
            candidates[idx]['bg_removed'] = True
            self.preview_candidates = candidates

            image_paths = [
                c['image_path'] for c in self.preview_candidates
                if 'error' not in c and 'image_path' in c
            ]

            return (
                image_paths,
                f"✅ Фон удален для изображения {idx} за {elapsed:.1f}с",
                f"✅ Фон успешно удален за {elapsed:.1f}с! Режим: {bg_removal_mode}",
            )

        except Exception as e:
            logger.error(f"Background removal error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return gr.update(), f"❌ Ошибка: {str(e)}", f"❌ Ошибка при удалении фона: {str(e)}"
