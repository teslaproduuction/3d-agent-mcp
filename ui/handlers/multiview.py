"""
Multiview regeneration handler.
"""
import gradio as gr
from utils.logger import get_logger

logger = get_logger(__name__)

# Map Radio index → view description used by generate_view_from_image
_VIEW_DESCRIPTION = {
    0: "front view",
    1: "back view",
    2: "left side view",
    3: "right side view",
}

_VIEW_NAME_RU = {
    0: "передний",
    1: "задний",
    2: "левый",
    3: "правый",
}


class MultiviewHandlersMixin:

    async def handle_regenerate_multiview(
        self,
        session_id: str,
        selected_multiview_index: str,
        regenerate_view_prompt: str,
        image_provider: str,
    ):
        """Regenerate one view in the multiview gallery with a custom prompt."""
        self.set_active_session(session_id)
        self.update_ui_setting('image_provider', image_provider)

        if not self.multiview_images:
            return gr.update(), "⚠️ Сначала сгенерируйте multi-view виды"

        try:
            idx = int(selected_multiview_index)
        except (TypeError, ValueError):
            return gr.update(), "⚠️ Выберите вид для регенерации"

        view_description = _VIEW_DESCRIPTION.get(idx, "front view")
        view_name_ru = _VIEW_NAME_RU.get(idx, f"вид {idx}")

        # Original image prompt stored in session — used as style/object anchor
        image_prompt = (self.ui_settings or {}).get('image_prompt', '')

        # Build effective prompt:
        # user edit instruction overrides / extends the original prompt
        if regenerate_view_prompt.strip():
            if image_prompt:
                # combine: keep object context, apply user edit
                effective_prompt = f"{image_prompt}. {regenerate_view_prompt.strip()}"
            else:
                effective_prompt = regenerate_view_prompt.strip()
        elif image_prompt:
            effective_prompt = image_prompt
        else:
            return gr.update(), "⚠️ Введите промпт для регенерации или сначала сгенерируйте промпт"

        logger.info(
            f"Regenerating {view_name_ru} view | view_desc={view_description} | "
            f"effective_prompt={effective_prompt[:80]}"
        )

        # Human camera descriptions for text-to-image models
        _view_text = {
            "front view":      "front view, facing camera directly",
            "back view":       "rear view, seen from behind",
            "left side view":  "left side profile view",
            "right side view": "right side profile view",
        }
        view_text = _view_text.get(view_description, view_description)

        try:
            base_image_path = self.multiview_images[0] if self.multiview_images else None
            user_edit = regenerate_view_prompt.strip()

            # Current view image (the one being edited) as img2img source
            current_view_path = self.multiview_images[idx] if idx < len(self.multiview_images) else None

            if user_edit:
                # User provided edit instruction → img2img on CURRENT view image.
                # FLUX img2img: preserves character structure, applies text edits.
                # denoise=0.65: moderate edit — keeps shape/colors, allows geometry changes.
                edit_prompt = (
                    f"{effective_prompt}, {view_text}, {user_edit}, "
                    f"3D render figurine, white background, studio lighting, "
                    f"same character same design same colors"
                )
                logger.info(f"img2img edit (denoise=0.65): {edit_prompt[:120]}")

                src_image = current_view_path or base_image_path
                if src_image:
                    result = await self.coordinator.image_api_client.img2img_edit(
                        image_path=src_image,
                        prompt=edit_prompt,
                        denoise=0.75,
                    )
                else:
                    # No source image at all — fall back to txt2img
                    result = await self.coordinator.image_api_client.generate_single(
                        prompt=edit_prompt,
                        style="realistic 3D render, white background",
                    )
            elif base_image_path:
                # No edit instruction → use Zero123Plus for view-consistent rotation
                results = await self.coordinator.image_api_client.generate_multiview_from_image(
                    base_image_path=base_image_path,
                    original_prompt=effective_prompt,
                    views=[view_description],
                )
                result = results[0] if results else {'error': 'No result from generator'}
            else:
                result = await self.coordinator.image_api_client.generate_single(
                    prompt=f"{effective_prompt}, {view_text}",
                    style="realistic 3D render, white background, product design",
                )

            if 'error' in result:
                raise Exception(result['error'])

            # Read-modify-write for Redis
            images = list(self.multiview_images)
            images[idx] = result['image_path']
            self.multiview_images = images

            logger.info(f"Successfully regenerated {view_name_ru} view: {result['image_path']}")
            return self.multiview_images, f"✅ {view_name_ru.capitalize()} вид успешно регенерирован!"

        except Exception as e:
            logger.error(f"Multiview regeneration error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return gr.update(), f"❌ Ошибка: {str(e)}"
