"""
Analytics tab — generation metrics, GCI analysis, resource tracking.
Feeds data for internship report charts.
"""
import gradio as gr


def build_analytics_tab() -> dict:
    """Build analytics tab. Must be called inside gr.Tabs() context."""

    with gr.Tab("Аналитика"):
        gr.Markdown("""
### Аналитика генераций
Временные затраты, ресурсы GPU/CPU/RAM, индекс геометрической сложности (GCI) по модели Фролова (2025).
        """)

        with gr.Row():
            refresh_btn = gr.Button("Обновить", variant="primary", size="sm", scale=0)

        # ── Summary cards ───────────────────────────────────────────────
        gr.Markdown("#### Сводка")
        with gr.Row():
            stat_total    = gr.Textbox(label="Генераций всего",    interactive=False, scale=1)
            stat_avg_time = gr.Textbox(label="Среднее время 3D",   interactive=False, scale=1)
            stat_avg_vram = gr.Textbox(label="Средний пик VRAM",   interactive=False, scale=1)
            stat_avg_face = gr.Textbox(label="Среднее полигонов",  interactive=False, scale=1)
            stat_avg_gci  = gr.Textbox(label="Средний GCI",        interactive=False, scale=1)
            stat_success  = gr.Textbox(label="С данными времени",  interactive=False, scale=1)

        # ── Time charts ─────────────────────────────────────────────────
        gr.Markdown("#### Временны́е затраты")
        with gr.Row():
            plot_time_breakdown = gr.Plot(label="Разбивка по этапам (сек)")
            plot_time_history   = gr.Plot(label="История времени генерации")

        # ── Resource charts ─────────────────────────────────────────────
        gr.Markdown("#### Ресурсы")
        with gr.Row():
            plot_resources = gr.Plot(label="Пиковое потребление ресурсов")

        # ── GCI charts ──────────────────────────────────────────────────
        gr.Markdown("""
#### Индекс геометрической сложности (GCI)

> **GCI = w₁·(Nf/A) + w₂·(C/L) + w₃·(Vc/Vt)**
> w₁=0.0002, w₂=0.0028, w₃=0.9970
> Порог: GCI < 0.5 → MAE < 0.3 мм | 0.5–0.8 → MAE ≈ 0.8–1.2 мм | ≥ 0.8 → MAE > 1.5 мм
        """)
        with gr.Row():
            plot_gci_dist  = gr.Plot(label="Распределение GCI")
            plot_gci_time  = gr.Plot(label="GCI vs Время генерации")

        # ── Model comparison ─────────────────────────────────────────────
        gr.Markdown("#### Сравнение моделей")
        plot_models = gr.Plot(label="Сравнение моделей (полигоны / GCI / время)")

        # ── Detailed table ───────────────────────────────────────────────
        gr.Markdown("#### Детальный журнал (последние 50)")
        table = gr.DataFrame(
            interactive=False,
            wrap=False,
        )

    outputs = [
        stat_total, stat_avg_time, stat_avg_vram,
        stat_avg_face, stat_avg_gci, stat_success,
        plot_time_breakdown, plot_time_history,
        plot_resources,
        plot_gci_dist, plot_models, plot_gci_time,
        table,
    ]

    return dict(
        analytics_refresh_btn=refresh_btn,
        analytics_stat_total=stat_total,
        analytics_stat_avg_time=stat_avg_time,
        analytics_stat_avg_vram=stat_avg_vram,
        analytics_stat_avg_face=stat_avg_face,
        analytics_stat_avg_gci=stat_avg_gci,
        analytics_stat_success=stat_success,
        analytics_plot_time_breakdown=plot_time_breakdown,
        analytics_plot_time_history=plot_time_history,
        analytics_plot_resources=plot_resources,
        analytics_plot_gci_dist=plot_gci_dist,
        analytics_plot_models=plot_models,
        analytics_plot_gci_time=plot_gci_time,
        analytics_table=table,
        analytics_outputs=outputs,
    )
