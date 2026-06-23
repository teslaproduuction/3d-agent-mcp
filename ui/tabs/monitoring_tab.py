"""
Monitoring tab — real-time hardware usage dashboard.
GPU stats from ComfyUI /system_stats, CPU/RAM from psutil.
"""
import gradio as gr


def build_monitoring_tab() -> dict:
    """Build the hardware monitoring tab. Must be called inside gr.Tabs() context."""
    with gr.Tab("Мониторинг"):
        gr.Markdown("### Загрузка оборудования")

        with gr.Row():
            refresh_btn = gr.Button("Обновить", variant="secondary", size="sm", scale=0)
            auto_refresh = gr.Checkbox(label="Авто-обновление (10 сек)", value=True, scale=0)

        # GPU block
        with gr.Group():
            gr.Markdown("#### GPU")
            with gr.Row():
                gpu_name      = gr.Textbox(label="Модель", interactive=False, scale=3)
                gpu_util      = gr.Textbox(label="Загрузка", interactive=False, scale=1)
                gpu_temp      = gr.Textbox(label="Температура", interactive=False, scale=1)
                gpu_power     = gr.Textbox(label="Мощность", interactive=False, scale=1)
                gpu_fan       = gr.Textbox(label="Вентилятор", interactive=False, scale=1)
            with gr.Row():
                gpu_vram_used = gr.Textbox(label="VRAM занято", interactive=False, scale=1)
                gpu_vram_free = gr.Textbox(label="VRAM свободно", interactive=False, scale=1)
                gpu_vram_total= gr.Textbox(label="VRAM всего", interactive=False, scale=1)
            gpu_vram_bar = gr.Slider(label="VRAM %", minimum=0, maximum=100,
                                     interactive=False, value=0)

        # CPU block
        with gr.Group():
            gr.Markdown("#### CPU")
            with gr.Row():
                cpu_util  = gr.Textbox(label="Загрузка", interactive=False, scale=1)
                cpu_temp  = gr.Textbox(label="Температура", interactive=False, scale=1)
                cpu_cores = gr.Textbox(label="Ядра", interactive=False, scale=1)
                cpu_freq  = gr.Textbox(label="Частота", interactive=False, scale=1)
            cpu_bar = gr.Slider(label="CPU %", minimum=0, maximum=100,
                                interactive=False, value=0)

        # RAM block
        with gr.Group():
            gr.Markdown("#### RAM")
            with gr.Row():
                ram_used  = gr.Textbox(label="Занято", interactive=False, scale=1)
                ram_free  = gr.Textbox(label="Свободно", interactive=False, scale=1)
                ram_total = gr.Textbox(label="Всего", interactive=False, scale=1)
            ram_bar = gr.Slider(label="RAM %", minimum=0, maximum=100,
                                interactive=False, value=0)

        # Time-series charts
        with gr.Group():
            gr.Markdown("#### История загрузки")
            gpu_chart = gr.LinePlot(
                x="time", y="VRAM %",
                title="GPU VRAM %",
                x_title="Время", y_title="%",
                height=200,
                y_lim=[0, 100],
            )
            cpu_chart = gr.LinePlot(
                x="time", y="CPU %",
                title="CPU %",
                x_title="Время", y_title="%",
                height=200,
                y_lim=[0, 100],
            )
            ram_chart = gr.LinePlot(
                x="time", y="RAM %",
                title="RAM %",
                x_title="Время", y_title="%",
                height=200,
                y_lim=[0, 100],
            )

        # Services block
        with gr.Group():
            gr.Markdown("#### Сервисы")
            services_table = gr.Dataframe(
                headers=["Сервис", "Статус", "CPU %", "RAM"],
                datatype=["str", "str", "str", "str"],
                interactive=False,
                row_count=8,
            )

        # Timer for auto-refresh
        monitor_timer = gr.Timer(value=10, active=False)

    monitoring_outputs = [
        gpu_name, gpu_util, gpu_temp, gpu_power, gpu_fan,
        gpu_vram_used, gpu_vram_free, gpu_vram_total, gpu_vram_bar,
        cpu_util, cpu_temp, cpu_cores, cpu_freq, cpu_bar,
        ram_used, ram_free, ram_total, ram_bar,
        services_table,
        gpu_chart, cpu_chart, ram_chart,
    ]

    return dict(
        monitoring_refresh_btn=refresh_btn,
        monitoring_auto_refresh=auto_refresh,
        monitoring_timer=monitor_timer,
        monitoring_gpu_name=gpu_name,
        monitoring_gpu_util=gpu_util,
        monitoring_gpu_temp=gpu_temp,
        monitoring_gpu_power=gpu_power,
        monitoring_gpu_fan=gpu_fan,
        monitoring_gpu_vram_used=gpu_vram_used,
        monitoring_gpu_vram_free=gpu_vram_free,
        monitoring_gpu_vram_total=gpu_vram_total,
        monitoring_gpu_vram_bar=gpu_vram_bar,
        monitoring_cpu_util=cpu_util,
        monitoring_cpu_temp=cpu_temp,
        monitoring_cpu_cores=cpu_cores,
        monitoring_cpu_freq=cpu_freq,
        monitoring_cpu_bar=cpu_bar,
        monitoring_ram_used=ram_used,
        monitoring_ram_free=ram_free,
        monitoring_ram_total=ram_total,
        monitoring_ram_bar=ram_bar,
        monitoring_services_table=services_table,
        monitoring_gpu_chart=gpu_chart,
        monitoring_cpu_chart=cpu_chart,
        monitoring_ram_chart=ram_chart,
        monitoring_outputs=monitoring_outputs,
    )
