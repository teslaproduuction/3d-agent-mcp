"""
Tab 1 — Preview candidates gallery + background removal.
"""
import gradio as gr


def build_preview_tab() -> dict:
    """Build the preview candidates tab. Must be called inside a gr.Tabs() context."""
    with gr.Tab("Превью-кандидаты (4 шт)"):
        gr.Markdown("### Выберите понравившееся изображение")
        preview_gallery = gr.Gallery(
            label="4 варианта превью",
            columns=2,
            rows=2,
            height=520,
            object_fit="contain",
            allow_preview=True,
            selected_index=None,
        )

        with gr.Row():
            remove_bg_btn = gr.Button(
                "Удалить фон",
                variant="secondary",
                size="sm",
            )
            bg_removal_mode = gr.Radio(
                choices=["Прозрачный фон", "Белый фон"],
                value="Прозрачный фон",
                label="Режим",
                scale=1,
            )

        bg_removal_status = gr.Textbox(
            label="Статус удаления фона",
            interactive=False,
            visible=False,
        )

    return dict(
        preview_gallery=preview_gallery,
        remove_bg_btn=remove_bg_btn,
        bg_removal_mode=bg_removal_mode,
        bg_removal_status=bg_removal_status,
    )
