"""
Tab 4 — Ready-to-print gallery + download options.
"""
import gradio as gr


def build_printable_tab() -> dict:
    """Build the printable models tab. Must be called inside a gr.Tabs() context."""
    with gr.Tab("Готово к печати"):
        gr.Markdown("### Интерактивное сравнение до и после обработки")

        with gr.Row():
            printable_before_model = gr.Model3D(
                label="До обработки",
                height=420,
            )
            printable_after_model = gr.Model3D(
                label="После обработки",
                height=420,
            )

        printable_heatmap_model = gr.Model3D(
            label="Тепловая карта изменения геометрии",
            height=520,
        )

        printable_compare_info = gr.Markdown(
            value="*Сгенерируйте модель, чтобы увидеть сравнение в 3D*"
        )

        gr.Markdown("### Опции загрузки")
        with gr.Row():
            download_single_btn = gr.Button("Скачать выбранную модель")
            download_all_btn = gr.Button("Скачать все модели (ZIP)")

        download_status = gr.Textbox(label="Статус загрузки", interactive=False)

    return dict(
        printable_before_model=printable_before_model,
        printable_after_model=printable_after_model,
        printable_heatmap_model=printable_heatmap_model,
        printable_compare_info=printable_compare_info,
        download_single_btn=download_single_btn,
        download_all_btn=download_all_btn,
        download_status=download_status,
    )
