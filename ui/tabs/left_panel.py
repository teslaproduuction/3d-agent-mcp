"""
Left input panel: description → prompt → image generation → 3D settings.
"""
import gradio as gr


def build_left_panel(local_models: list, config) -> dict:
    """
    Build the left control column inside an existing gr.Row() context.
    Returns a flat dict of all Gradio components for event wiring.
    """
    with gr.Column(scale=1):
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
            label="Редактируемый промпт (можете изменить)",
            placeholder="Сгенерированный промпт появится здесь...",
            lines=4,
            interactive=True,
            show_label=False,
        )

        generate_images_btn = gr.Button("Сгенерировать 4 превью", variant="secondary", size="lg")

        gr.Markdown("### Выбор изображения")
        selected_image_index = gr.Radio(
            choices=["0", "1", "2", "3"],
            label="Выберите понравившееся изображение",
            value=None,
        )

        use_multiview = gr.Checkbox(
            label="Использовать Multi-view (лучшее качество)",
            value=True,
        )

        generate_3d_btn = gr.Button("Генерировать 3D модель", variant="primary", size="lg")

        with gr.Accordion("Настройки", open=False):
            gr.Markdown("#### Генератор изображений")
            image_provider = gr.Radio(
                choices=["gpt-image-1", "dalle3", "sdxl", "flux", "local"],
                value="local",
                label="Провайдер",
                info="local: FLUX.1-schnell (ComfyUI) | gpt-image-1: OpenAI API",
            )

            gr.Markdown("#### LLM для агентов")
            llm_provider = gr.Radio(
                choices=["openai", "anthropic", "google", "ollama"],
                value="ollama",
                label="LLM Провайдер",
                info="OpenAI: GPT-4o | Anthropic: Claude Sonnet | Google: Gemini Flash | Ollama: Локально",
            )

            llm_model = gr.Dropdown(
                choices=["qwen2.5:32b", "qwen2.5:7b", "qwen2.5:3b", "qwen2.5:1.5b", "llama3.2:1b",
                         "gpt-4o-mini", "gpt-4o", "o1-mini", "o3-mini"],
                value="qwen2.5:32b",
                label="Модель LLM",
                info="qwen2.5:32b: H800 81GB | qwen2.5:7b: H800 быстрее | qwen2.5:3b: RTX 5080 | gpt-4o-mini: Облако",
            )

            gr.Markdown("#### 3D Генерация")
            generation_mode = gr.Radio(
                choices=["API (Cloud)", "Локальная модель"],
                value="Локальная модель",
                label="Режим генерации",
                info="API = Tripo/Meshy через интернет, Локальная = на вашем ПК",
            )

            api_provider = gr.Radio(
                choices=["tripo", "meshy"],
                value="tripo",
                label="API провайдер",
                visible=True,
            )

            # Build local model choices from config
            local_model_choices = []
            local_model_default = None
            if local_models:
                for m in local_models:
                    local_model_choices.append((m.get('display_name', m['name']), m['name']))
                models_config = config.get('default_settings.local_3d_models', {})
                local_model_default = models_config.get('default_model', local_models[0]['name'])
            else:
                local_model_choices = [
                    ("TripoSR (быстро)",         "triposr"),
                    ("Shap-E (качество)",         "shap-e"),
                    ("Instant3D (балансированно)", "instant3d"),
                ]
                local_model_default = "triposr"

            local_model = gr.Radio(
                choices=local_model_choices,
                value=local_model_default,
                label="Локальная модель",
                visible=False,
                info="Модели загружены из конфигурации",
            )

            gr.Markdown("#### Постобработка")
            enable_intelligent_processing = gr.Checkbox(label="Интеллектуальная обработка", value=True)
            auto_orient = gr.Checkbox(label="Авто-оптимизация ориентации (OrcaSlicer)", value=True,
                                      info="Использует алгоритм OrcaSlicer для поиска оптимальной ориентации")
            generate_supports = gr.Checkbox(label="Рекомендации для поддержек", value=True)
            max_overhang_angle = gr.Slider(
                minimum=30, maximum=60, value=45, step=5, label="Макс. угол свеса (°)"
            )

            gr.Markdown("#### Сделать нависания пригодными для печати")
            make_overhangs_printable = gr.Checkbox(
                label="Исправить нависания (конический алгоритм)",
                value=False,
                info="Изменяет геометрию модели, убирая нависания выше порогового угла. "
                     "Аналог функции OrcaSlicer «Делать нависания пригодными для печати».",
            )
            with gr.Column(visible=False) as overhang_settings_col:
                overhang_printable_angle = gr.Slider(
                    minimum=0, maximum=90, value=55, step=1,
                    label="Макс. угол нависаний (°)",
                    info="0° = всё коническое, 55° = только крутые нависания, 90° = без изменений",
                )
                overhang_printable_holes = gr.Slider(
                    minimum=0, maximum=200, value=0, step=1,
                    label="Заполнять отверстия до (мм²)",
                    info="Максимальная площадь отверстий в основании, которые будут заполнены",
                )
                overhang_method = gr.Radio(
                    choices=[("Воксели (надёжно)", "voxel"), ("Вершины (качество)", "vertex")],
                    value="voxel",
                    label="Метод исправления нависаний",
                    info="Воксели: перестраивает геометрию, всегда корректно. Вершины: двигает только выступающие вершины, сохраняет детали.",
                )


        status_text = gr.Textbox(label="Статус", interactive=False, show_label=False)

    return dict(
        user_description=user_description,
        random_idea_btn=random_idea_btn,
        generate_prompt_btn=generate_prompt_btn,
        image_prompt=image_prompt,
        generate_images_btn=generate_images_btn,
        selected_image_index=selected_image_index,
        use_multiview=use_multiview,
        generate_3d_btn=generate_3d_btn,
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
        overhang_settings_col=overhang_settings_col,
        overhang_printable_angle=overhang_printable_angle,
        overhang_printable_holes=overhang_printable_holes,
        overhang_method=overhang_method,
        status_text=status_text,
    )
