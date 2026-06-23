"""
Orientation handler mixin — Surface-on-Bed feature.

Provides methods that are called by Gradio event handlers in events.py:
  - handle_detect_flat_faces(model_path) → viewer_html, face_dropdown, apply_btn, info
  - handle_face_click(model_path, face_json) → model_viewer, viewer_html, info
  - handle_apply_face_to_bed(model_path, face_label) → model_viewer, viewer_html, info
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

import gradio as gr
import numpy as np

from agents.surface_on_bed import detect_flat_faces, apply_face_to_bed_from_file
from ui.components.surface_viewer import create_interactive_viewer
from utils.logger import get_logger

logger = get_logger(__name__)


class OrientationHandlersMixin:
    """Mixin added to the main GradioInterface class."""

    def handle_detect_flat_faces(self, session_id: str, model_path: Optional[str]):
        """
        Detect flat face groups in the current model and build the interactive viewer.

        Called when user presses "Найти плоские грани".
        Returns: (viewer_html, face_dropdown_update, apply_btn_update, info_markdown)
        """
        self.set_active_session(session_id)

        if not model_path or not os.path.exists(str(model_path)):
            return (
                "<p style='color:#ff6b6b'>Сначала загрузите или сгенерируйте модель.</p>",
                gr.update(choices=[], visible=False),
                gr.update(visible=False),
                "",
            )

        try:
            import trimesh
            mesh = trimesh.load(str(model_path), force="mesh")
            if isinstance(mesh, trimesh.Scene):
                mesh = trimesh.util.concatenate(list(mesh.geometry.values()))

            groups = detect_flat_faces(mesh)

            if not groups:
                return (
                    "<p style='color:#feca57'>Плоские грани не найдены.</p>",
                    gr.update(choices=[], visible=False),
                    gr.update(visible=False),
                    "Не удалось найти плоских граней для ориентации.",
                )

            viewer_html = create_interactive_viewer(str(model_path), groups, uid="main")
            choices = [g.label for g in groups]

            info = (
                f"**Найдено плоских граней: {len(groups)}**  \n"
                + "  \n".join(f"- {g.label}" for g in groups)
            )

            return (
                viewer_html,
                gr.update(choices=choices, value=choices[0], visible=True),
                gr.update(visible=True),
                info,
            )

        except Exception as exc:
            logger.error(f"handle_detect_flat_faces error: {exc}", exc_info=True)
            return (
                f"<p style='color:#ff6b6b'>Ошибка: {exc}</p>",
                gr.update(choices=[], visible=False),
                gr.update(visible=False),
                f"Ошибка при анализе граней: {exc}",
            )

    def handle_face_click(self, session_id: str, model_path: Optional[str], face_json: Optional[str]):
        """
        Called when the user clicks a face in the Three.js viewer.
        `face_json` is a JSON string: {"group_index": int, "normal": [x, y, z]}

        Returns: (model_viewer_update, viewer_html, info_markdown)
        """
        self.set_active_session(session_id)

        if not face_json or not face_json.strip():
            return gr.update(), gr.update(), ""

        try:
            data = json.loads(face_json)
            normal = np.array(data["normal"], dtype=float)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning(f"handle_face_click: bad JSON: {exc}")
            return gr.update(), gr.update(), f"Ошибка чтения данных грани: {exc}"

        return self._rotate_to_face(model_path, normal)

    def handle_apply_face_to_bed(self, session_id: str, model_path: Optional[str], face_label: Optional[str]):
        """
        Called when user selects a face from the dropdown and presses Apply.
        We store face group info in the viewer state; here we re-detect and match by label.

        Returns: (model_viewer_update, viewer_html, info_markdown)
        """
        self.set_active_session(session_id)

        if not model_path or not os.path.exists(str(model_path)):
            return gr.update(), gr.update(), "Модель не найдена."

        if not face_label:
            return gr.update(), gr.update(), "Выберите грань из списка."

        try:
            import trimesh
            mesh = trimesh.load(str(model_path), force="mesh")
            if isinstance(mesh, trimesh.Scene):
                mesh = trimesh.util.concatenate(list(mesh.geometry.values()))

            groups = detect_flat_faces(mesh)
            target = next((g for g in groups if g.label == face_label), None)

            if target is None:
                return gr.update(), gr.update(), f"Грань '{face_label}' не найдена."

            return self._rotate_to_face(model_path, target.normal)

        except Exception as exc:
            logger.error(f"handle_apply_face_to_bed error: {exc}", exc_info=True)
            return gr.update(), gr.update(), f"Ошибка: {exc}"

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _rotate_to_face(self, model_path: Optional[str], face_normal: np.ndarray):
        """Rotate model so face_normal points down, save, update viewer."""
        if not model_path or not os.path.exists(str(model_path)):
            return gr.update(), gr.update(), "Модель не найдена."

        try:
            import trimesh

            # Build output path (overwrite printable version)
            base, ext = os.path.splitext(str(model_path))
            if not base.endswith("_printable"):
                output_path = base + "_printable" + (ext or ".stl")
            else:
                output_path = model_path

            # Always output as STL
            if not output_path.endswith(".stl"):
                output_path = os.path.splitext(output_path)[0] + ".stl"

            apply_face_to_bed_from_file(str(model_path), face_normal, output_path)

            # Rebuild viewer with updated mesh
            mesh = trimesh.load(output_path, force="mesh")
            if isinstance(mesh, trimesh.Scene):
                mesh = trimesh.util.concatenate(list(mesh.geometry.values()))
            groups = detect_flat_faces(mesh)
            viewer_html = create_interactive_viewer(output_path, groups, uid=str(int(time.time())))

            models = self.generated_models
            if models:
                selected_idx = self.selected_model_index
                if not isinstance(selected_idx, int) or selected_idx < 0 or selected_idx >= len(models):
                    selected_idx = 0

                updated_models = list(models)
                updated_model = dict(updated_models[selected_idx])
                updated_model['model_file'] = output_path
                updated_models[selected_idx] = updated_model
                self.generated_models = updated_models
                self.selected_model_index = selected_idx

            info = f"Модель повёрнута. Грань: {np.round(face_normal, 3).tolist()}"
            return output_path, viewer_html, info

        except Exception as exc:
            logger.error(f"_rotate_to_face error: {exc}", exc_info=True)
            return gr.update(), gr.update(), f"Ошибка поворота: {exc}"
