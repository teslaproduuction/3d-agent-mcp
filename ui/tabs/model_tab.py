"""
Tab 3 — 3D model viewer + AI analysis + Surface-on-Bed orientation.
"""
import gradio as gr


def build_model_tab() -> dict:
    """Build the 3D model tab. Must be called inside a gr.Tabs() context."""
    with gr.Tab("3D Модели"):
        gr.Markdown("### Сгенерированные 3D модели")

        with gr.Row():
            model_viewer = gr.Model3D(label="3D Превью", height=500)

        with gr.Row():
            with gr.Column():
                model_selector = gr.Dropdown(
                    label="Выбрать модель",
                    choices=[],
                    interactive=True,
                )

        # ── Surface-on-Bed ─────────────────────────────────────────────────
        with gr.Accordion("Ориентация по грани (Surface-on-Bed)", open=False):
            gr.Markdown(
                "Нажмите **«Найти плоские грани»**, чтобы обнаружить плоские "
                "поверхности модели. Затем кликните на подсвеченную грань прямо "
                "в 3D-просмотрщике или выберите из списка — модель повернётся "
                "этой гранью вниз."
            )

            detect_faces_btn = gr.Button("Найти плоские грани", variant="secondary")

            # Interactive Three.js viewer (populated after detect_faces_btn click)
            surface_viewer = gr.HTML(
                value="",
                label="Интерактивный просмотр граней",
            )

            # Hidden textbox — receives face JSON from Three.js click handler
            surface_face_input = gr.Textbox(
                value="",
                visible=False,
                elem_id="surface_face_input_main",
            )

            with gr.Row(visible=True):
                face_dropdown = gr.Dropdown(
                    label="Или выберите грань из списка",
                    choices=[],
                    visible=False,
                    interactive=True,
                )
                apply_face_btn = gr.Button(
                    "Применить ориентацию",
                    variant="primary",
                    visible=False,
                )

            face_result_info = gr.Markdown(value="", visible=True)

        # ── AI Analysis ────────────────────────────────────────────────────
        with gr.Accordion("AI Анализ", open=True):
            analysis_display = gr.Markdown(value="*Анализ пока недоступен*")

        with gr.Accordion("Рассуждения агента", open=True):
            reasoning_display = gr.Textbox(
                label="Почему были приняты эти решения",
                lines=5,
                interactive=False,
                show_label=False,
            )

        metadata_display = gr.JSON(label="Метаданные для печати", visible=True)

    return dict(
        model_viewer=model_viewer,
        model_selector=model_selector,
        analysis_display=analysis_display,
        reasoning_display=reasoning_display,
        metadata_display=metadata_display,
        # Surface-on-Bed components
        detect_faces_btn=detect_faces_btn,
        surface_viewer=surface_viewer,
        surface_face_input=surface_face_input,
        face_dropdown=face_dropdown,
        apply_face_btn=apply_face_btn,
        face_result_info=face_result_info,
    )
