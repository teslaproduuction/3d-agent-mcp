"""
Event wiring для упрощённого интерфейса /ystu.
Аналогично events.py, но без обработки настроек.
"""


def wire_events_ystu(app, c: dict):
    """
    Подключает события упрощённого интерфейса ЯГТУ.

    Parameters
    ----------
    app : GradioInterface
        Экземпляр приложения со всеми обработчиками.
    c : dict
        Плоский dict компонентов от tab/panel builders.
    """

    # ── Случайная идея ────────────────────────────────────────────────────
    c['random_idea_btn'].click(
        app.handle_random_idea,
        inputs=[c['session_id'], c['llm_provider'], c['llm_model']],
        outputs=[c['user_description'], c['status_text']],
    )

    # ── Генерация промпта ─────────────────────────────────────────────────
    c['generate_prompt_btn'].click(
        app.handle_generate_prompt,
        inputs=[c['session_id'], c['user_description'], c['llm_provider'], c['llm_model']],
        outputs=[c['image_prompt'], c['status_text']],
    )

    # ── Генерация изображений ─────────────────────────────────────────────
    c['generate_images_btn'].click(
        app.handle_generate_images,
        inputs=[c['session_id'], c['image_prompt'], c['image_provider']],
        outputs=[c['preview_gallery'], c['status_text']],
    )

    # ── Удаление фона ─────────────────────────────────────────────────────
    c['remove_bg_btn'].click(
        app.handle_remove_background,
        inputs=[c['session_id'], c['selected_image_index'], c['bg_removal_mode']],
        outputs=[c['preview_gallery'], c['bg_removal_status'], c['status_text']],
    )

    # ── Генерация 3D модели ───────────────────────────────────────────────
    c['generate_3d_btn'].click(
        app.handle_generate_3d,
        inputs=[
            c['session_id'],
            c['selected_image_index'],
            c['use_multiview'],
            c['image_prompt'],
            c['image_provider'],
            c['generation_mode'],
            c['api_provider'],
            c['local_model'],
            c['llm_provider'],
            c['llm_model'],
            c['enable_intelligent_processing'],
            c['auto_orient'],
            c['generate_supports'],
            c['max_overhang_angle'],
            c['make_overhangs_printable'],
            c['overhang_printable_angle'],
            c['overhang_printable_holes'],
        ],
        outputs=[
            c['multiview_gallery'],
            c['model_viewer'],
            c['model_selector'],
            c['analysis_display'],
            c['reasoning_display'],
            c['metadata_display'],
            c['printable_before_model'],
            c['printable_after_model'],
            c['printable_heatmap_model'],
            c['printable_compare_info'],
            c['status_text'],
        ],
    )

    # ── Выбор модели → обновление просмотрщика ────────────────────────────
    c['model_selector'].change(
        app.on_model_select,
        inputs=[c['session_id'], c['model_selector']],
        outputs=[
            c['model_viewer'],
            c['analysis_display'],
            c['reasoning_display'],
            c['metadata_display'],
            c['printable_before_model'],
            c['printable_after_model'],
            c['printable_heatmap_model'],
            c['printable_compare_info'],
        ],
    )

    # ── Multi-view: регенерация одного ракурса ────────────────────────────
    c['regenerate_view_btn'].click(
        app.handle_regenerate_multiview,
        inputs=[
            c['session_id'],
            c['selected_multiview_index'],
            c['regenerate_view_prompt'],
            c['image_provider'],
        ],
        outputs=[c['multiview_gallery'], c['regenerate_status']],
    )

    # ── Multi-view: переход к 3D ──────────────────────────────────────────
    c['continue_to_3d_btn'].click(
        app.handle_continue_to_3d,
        inputs=[
            c['session_id'],
            c['generation_mode'],
            c['api_provider'],
            c['local_model'],
            c['llm_provider'],
            c['llm_model'],
            c['enable_intelligent_processing'],
            c['auto_orient'],
            c['generate_supports'],
            c['max_overhang_angle'],
            c['make_overhangs_printable'],
            c['overhang_printable_angle'],
            c['overhang_printable_holes'],
        ],
        outputs=[
            c['model_viewer'],
            c['model_selector'],
            c['analysis_display'],
            c['reasoning_display'],
            c['metadata_display'],
            c['printable_before_model'],
            c['printable_after_model'],
            c['printable_heatmap_model'],
            c['printable_compare_info'],
            c['status_text'],
        ],
    )

    # ── Surface-on-Bed: обнаружение плоских граней ────────────────────────
    c['detect_faces_btn'].click(
        app.handle_detect_flat_faces,
        inputs=[c['session_id'], c['model_viewer']],
        outputs=[
            c['surface_viewer'],
            c['face_dropdown'],
            c['apply_face_btn'],
            c['face_result_info'],
        ],
    )

    c['surface_face_input'].change(
        app.handle_face_click,
        inputs=[c['session_id'], c['model_viewer'], c['surface_face_input']],
        outputs=[c['model_viewer'], c['surface_viewer'], c['face_result_info']],
    )

    c['apply_face_btn'].click(
        app.handle_apply_face_to_bed,
        inputs=[c['session_id'], c['model_viewer'], c['face_dropdown']],
        outputs=[c['model_viewer'], c['surface_viewer'], c['face_result_info']],
    )
