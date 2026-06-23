"""
Event wiring — connects all Gradio components to their handler methods.
Called once inside build_interface() after all tab builders have run.
"""
import gradio as gr


def wire_events(app, c: dict):
    """
    Wire up every button/radio/dropdown to its handler.

    Parameters
    ----------
    app : GradioInterface
        The fully assembled app instance (has all handler methods via mixins).
    c : dict
        Flat dict of all Gradio components returned by the tab/panel builders.
    """

    # ── Make overhangs printable: show/hide angle and hole sliders ────────
    def persist_setting(setting_key):
        def _persist(session_id, value):
            app.persist_ui_setting(session_id, setting_key, value)
        return _persist

    c['make_overhangs_printable'].change(
        lambda v: gr.update(visible=v),
        inputs=[c['make_overhangs_printable']],
        outputs=[c['overhang_settings_col']],
        queue=False,
        show_progress="hidden",
    )

    # ── Generation-mode toggle: show API provider OR local model radio ─────
    c['generation_mode'].change(
        lambda mode: (gr.update(visible=mode == "API (Cloud)"), gr.update(visible=mode == "Локальная модель")),
        inputs=[c['generation_mode']],
        outputs=[c['api_provider'], c['local_model']],
        queue=False,
    )

    # ── LLM provider → update model dropdown ──────────────────────────────
    def update_llm_models(session_id, provider):
        info_map = {
            "openai": "gpt-4o-mini: $0.15/$0.60 (рекомендуется) | gpt-4o: $5/$15",
            "anthropic": "Sonnet: $3/$15 | Opus: $15/$75 | Haiku: $0.25/$1.25",
            "google": "Flash: $0.10/$0.40 | Pro: $1.25/$5",
            "ollama": "Локальные модели (бесплатно, требуется Docker)",
        }

        p = app._llm_presets(provider)
        app.persist_ui_setting(session_id, 'llm_provider', provider)
        app.persist_ui_setting(session_id, 'llm_model', p["value"])
        return gr.update(choices=p["choices"], value=p["value"], info=info_map.get(provider, info_map["openai"]))

    c['llm_provider'].change(
        update_llm_models,
        inputs=[c['session_id'], c['llm_provider']],
        outputs=[c['llm_model']],
    )

    # NOTE:
    # We intentionally avoid no-output `.change(...)` handlers here.
    # In some Gradio/Svelte combinations these can trigger reactive loops
    # (effect_update_depth_exceeded) on the client.

    # ── Random idea ────────────────────────────────────────────────────────
    c['random_idea_btn'].click(
        app.handle_random_idea,
        inputs=[c['session_id'], c['llm_provider'], c['llm_model']],
        outputs=[c['user_description'], c['status_text']],
    )

    # ── Prompt generation ──────────────────────────────────────────────────
    c['generate_prompt_btn'].click(
        app.handle_generate_prompt,
        inputs=[c['session_id'], c['user_description'], c['llm_provider'], c['llm_model']],
        outputs=[c['image_prompt'], c['status_text']],
    )

    # ── Image generation ───────────────────────────────────────────────────
    c['generate_images_btn'].click(
        app.handle_generate_images,
        inputs=[c['session_id'], c['image_prompt'], c['image_provider']],
        outputs=[c['preview_gallery'], c['status_text']],
    )

    # ── Background removal ─────────────────────────────────────────────────
    c['remove_bg_btn'].click(
        app.handle_remove_background,
        inputs=[c['session_id'], c['selected_image_index'], c['bg_removal_mode']],
        outputs=[c['preview_gallery'], c['bg_removal_status'], c['status_text']],
    )

    # ── 3D generation (single image or multiview) ──────────────────────────
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
            c['overhang_method'],
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

    # ── Model selector → update viewer + analysis ──────────────────────────
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

    # ── Multiview: regenerate one view ─────────────────────────────────────
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

    # ── Multiview: continue to 3D ──────────────────────────────────────────
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
            c['overhang_method'],
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

    # ── Surface-on-Bed: detect flat faces ─────────────────────────────────
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

    # ── Surface-on-Bed: face clicked in Three.js viewer ───────────────────
    c['surface_face_input'].change(
        app.handle_face_click,
        inputs=[c['session_id'], c['model_viewer'], c['surface_face_input']],
        outputs=[c['model_viewer'], c['surface_viewer'], c['face_result_info']],
    )

    # ── Surface-on-Bed: apply from dropdown ───────────────────────────────
    c['apply_face_btn'].click(
        app.handle_apply_face_to_bed,
        inputs=[c['session_id'], c['model_viewer'], c['face_dropdown']],
        outputs=[c['model_viewer'], c['surface_viewer'], c['face_result_info']],
    )

    # ── Hardware monitoring ────────────────────────────────────────────────────
    _mon_out = c['monitoring_outputs']

    c['monitoring_refresh_btn'].click(
        app.handle_get_monitoring_stats,
        inputs=[c['session_id']],
        outputs=_mon_out,
    )

    c['monitoring_timer'].tick(
        app.handle_get_monitoring_stats,
        inputs=[c['session_id']],
        outputs=_mon_out,
    )

    c['monitoring_auto_refresh'].change(
        lambda enabled: gr.Timer(active=enabled),
        inputs=[c['monitoring_auto_refresh']],
        outputs=[c['monitoring_timer']],
    )

    # ── Analytics tab ─────────────────────────────────────────────────────
    _ana_out = c['analytics_outputs']

    c['analytics_refresh_btn'].click(
        app.handle_refresh_analytics,
        inputs=[],
        outputs=_ana_out,
    )
