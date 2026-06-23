"""
Упрощённая левая панель для страницы /ystu.
Без настроек — только ввод описания и кнопки генерации.
Скрытые состояния хранят значения настроек по умолчанию.
"""
import gradio as gr


def build_ystu_left_panel(local_models: list, config) -> dict:
    """
    Упрощённая левая панель без аккордеона настроек.
    Возвращает плоский dict компонентов для wire_events_ystu().
    """
    # Определяем локальную модель по умолчанию из конфигурации
    local_model_default = None
    if local_models:
        models_config = config.get('default_settings.local_3d_models', {})
        local_model_default = models_config.get('default_model', local_models[0]['name'])
    else:
        local_model_default = "triposr"

    with gr.Column(scale=1, min_width=420, elem_classes=["ystu-left-pane"]):
        gr.Markdown("### Описание объекта")
        user_description = gr.Textbox(
            label="Что вы хотите создать?",
            placeholder="Пример: Органайзер для стола с подставкой для ручек и телефона",
            lines=3,
            show_label=True,
        )

        with gr.Row():
            random_idea_btn = gr.Button("Случайная идея", variant="secondary", size="sm", scale=1)
            generate_prompt_btn = gr.Button("Сгенерировать промпт", variant="secondary", size="sm", scale=2)

        gr.Markdown("### Промпт для изображения")
        image_prompt = gr.Textbox(
            label="Редактируемый промпт",
            placeholder="Сгенерированный промпт появится здесь...",
            lines=4,
            interactive=True,
            show_label=False,
        )

        generate_images_btn = gr.Button("Сгенерировать 4 варианта", variant="secondary", size="lg")

        gr.Markdown("### Выбор изображения")
        selected_image_index = gr.Radio(
            choices=["0", "1", "2", "3"],
            label="Выберите понравившееся изображение",
            value=None,
        )

        use_multiview = gr.Checkbox(
            label="Использовать Multi-view (повышенное качество)",
            value=True,
        )

        generate_3d_btn = gr.Button("Генерировать 3D модель", variant="primary", size="lg")

        status_text = gr.Textbox(label="Статус", interactive=False, show_label=False)

        # Скрытые состояния с настройками по умолчанию
        image_provider = gr.State("local")
        llm_provider = gr.State("ollama")
        llm_model = gr.State("qwen2.5:7b")
        generation_mode = gr.State("Локальная модель")
        api_provider = gr.State("tripo")
        local_model = gr.State(local_model_default)
        enable_intelligent_processing = gr.State(True)
        auto_orient = gr.State(True)
        generate_supports = gr.State(True)
        max_overhang_angle = gr.State(45)
        make_overhangs_printable = gr.State(False)
        overhang_printable_angle = gr.State(55.0)
        overhang_printable_holes = gr.State(0.0)
        bg_removal_mode = gr.State("Прозрачный фон")

    return dict(
        user_description=user_description,
        random_idea_btn=random_idea_btn,
        generate_prompt_btn=generate_prompt_btn,
        image_prompt=image_prompt,
        generate_images_btn=generate_images_btn,
        selected_image_index=selected_image_index,
        use_multiview=use_multiview,
        generate_3d_btn=generate_3d_btn,
        status_text=status_text,
        # Hidden states
        image_provider=image_provider,
        llm_provider=llm_provider,
        llm_model=llm_model,
        generation_mode=generation_mode,
        api_provider=api_provider,
        local_model=local_model,
        enable_intelligent_processing=enable_intelligent_processing,
        auto_orient=auto_orient,
        generate_supports=generate_supports,
        max_overhang_angle=max_overhang_angle,
        make_overhangs_printable=make_overhangs_printable,
        overhang_printable_angle=overhang_printable_angle,
        overhang_printable_holes=overhang_printable_holes,
        bg_removal_mode=bg_removal_mode,
    )
