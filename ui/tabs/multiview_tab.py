"""
Tab 2 — Multi-view images gallery + per-view regeneration.
"""
import gradio as gr


def build_multiview_tab() -> dict:
    """Build the multiview tab. Must be called inside a gr.Tabs() context."""
    with gr.Tab("Multi-view виды"):
        gr.Markdown("### Сгенерированные виды объекта")
        gr.Markdown("*Front, Back, Left, Right views*")
        multiview_gallery = gr.Gallery(
            label="Multi-view изображения",
            columns=4,
            height=360,
            object_fit="contain",
            selected_index=None,
        )

        with gr.Accordion("Редактирование видов", open=False):
            gr.Markdown("Выберите вид для редактирования и введите новый промпт")
            selected_multiview_index = gr.Radio(
                choices=[
                    ("Front (передний)", "0"),
                    ("Back (задний)",    "1"),
                    ("Left (левый)",     "2"),
                    ("Right (правый)",   "3"),
                ],
                value="0",
                label="Выберите вид для редактирования",
                interactive=True,
            )

            regenerate_view_prompt = gr.Textbox(
                label="Промпт для регенерации выбранного вида",
                placeholder="Например: same object, view from the right side, white background",
                lines=2,
                interactive=True,
            )

            with gr.Row():
                regenerate_view_btn = gr.Button(
                    "Регенерировать выбранный вид",
                    variant="secondary",
                    size="sm",
                )
                continue_to_3d_btn = gr.Button(
                    "Продолжить к 3D генерации",
                    variant="primary",
                    size="sm",
                )

            regenerate_status = gr.Textbox(
                label="Статус регенерации",
                interactive=False,
                visible=True,
            )

    return dict(
        multiview_gallery=multiview_gallery,
        selected_multiview_index=selected_multiview_index,
        regenerate_view_prompt=regenerate_view_prompt,
        regenerate_view_btn=regenerate_view_btn,
        continue_to_3d_btn=continue_to_3d_btn,
        regenerate_status=regenerate_status,
    )
