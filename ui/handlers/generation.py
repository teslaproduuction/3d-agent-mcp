"""
3D generation handlers: single-image, multiview-to-3D, and legacy scene generation.
"""
import time
import asyncio

import gradio as gr
from utils.logger import get_logger

logger = get_logger(__name__)

# Shorthand for the "no model yet" tuple returned from handle_generate_3d
_NO_MODEL = (
    [],
    None,
    gr.update(choices=[], value=None),
    "*Выберите изображение*",
    "",
    {},
    None,
    None,
    None,
    "*Сравнение до/после пока недоступно*",
    "⚠️ Выберите изображение из превью",
)


class GenerationHandlersMixin:

    async def handle_generate_3d(
        self,
        session_id: str,
        selected_image_index: str,
        use_multiview: bool,
        image_prompt: str,
        image_provider: str,
        generation_mode: str,
        api_provider: str,
        local_model: str,
        llm_provider: str,
        llm_model: str,
        enable_intelligent_processing: bool,
        auto_orient: bool,
        generate_supports: bool,
        max_overhang_angle: float,
        make_overhangs_printable: bool = False,
        overhang_printable_angle: float = 55.0,
        overhang_printable_holes: float = 0.0,
        overhang_method: str = "voxel",
    ):
        """Generate 3D model from selected preview image."""
        self.set_active_session(session_id)
        self.update_ui_setting('use_multiview', use_multiview)
        self.update_ui_setting('image_provider', image_provider)
        self.update_ui_setting('generation_mode', generation_mode)
        self.update_ui_setting('api_provider', api_provider)
        self.update_ui_setting('local_model', local_model)
        self.update_ui_setting('llm_provider', llm_provider)
        self.update_ui_setting('llm_model', llm_model)
        self.update_ui_setting('enable_intelligent_processing', enable_intelligent_processing)
        self.update_ui_setting('auto_orient', auto_orient)
        self.update_ui_setting('generate_supports', generate_supports)
        self.update_ui_setting('max_overhang_angle', max_overhang_angle)
        self.update_ui_setting('make_overhangs_printable', make_overhangs_printable)
        self.update_ui_setting('overhang_printable_angle', overhang_printable_angle)
        self.update_ui_setting('overhang_printable_holes', overhang_printable_holes)
        self.update_ui_setting('overhang_method', overhang_method)

        if selected_image_index is None:
            return _NO_MODEL

        try:
            idx = int(selected_image_index)
            if idx >= len(self.preview_candidates):
                return (
                    [],
                    None,
                    gr.update(choices=[], value=None),
                    "*Ошибка выбора*",
                    "",
                    {},
                    None,
                    None,
                    None,
                    "*Сравнение до/после пока недоступно*",
                    "❌ Неверный индекс изображения",
                )

            selected_candidate = self.preview_candidates[idx]
            if 'error' in selected_candidate:
                return (
                    [],
                    None,
                    gr.update(choices=[], value=None),
                    "*Ошибка*",
                    "",
                    {},
                    None,
                    None,
                    None,
                    "*Сравнение до/после пока недоступно*",
                    "❌ Выбранное изображение содержит ошибку",
                )

            selected_image_path = selected_candidate['image_path']
            logger.info(f"Generating 3D from image {idx}: {selected_image_path}")

            multiview_paths = []

            # ── Step 1: optional multiview ─────────────────────────────────
            if use_multiview:
                logger.info("Generating multi-view images...")
                multiview_started_at = time.perf_counter()
                multiview_results = await self.coordinator.image_api_client.generate_multiview_from_image(
                    base_image_path=selected_image_path,
                    original_prompt=image_prompt,
                )
                multiview_paths = [selected_image_path] + [
                    r['image_path'] for r in multiview_results
                    if 'error' not in r and 'image_path' in r
                ]
                self.multiview_images = multiview_paths
                self.selected_multiview_index = "0"
                elapsed = time.perf_counter() - multiview_started_at
                logger.info(
                    f"Generated {len(multiview_paths)} multi-view images in {elapsed:.1f}s"
                )

                # Return early — let user review/edit views first
                return (
                    multiview_paths, None,
                    gr.update(choices=[], value=None),
                    "*Multi-view виды сгенерированы*",
                    "Отредактируйте виды при необходимости и нажмите 'Продолжить к 3D генерации'",
                    {},
                    None,
                    None,
                    None,
                    "*Сравнение появится после генерации 3D модели*",
                    f"✅ Сгенерировано {len(multiview_paths)} multi-view видов! Перейдите на вкладку 'Multi-view виды' для редактирования",
                )

            # ── Step 2: generate 3D model ──────────────────────────────────
            from utils.metrics_collector import GenerationRecord, save_record
            _t_total = time.perf_counter()
            _settings = self.ui_settings
            rec = GenerationRecord(
                session_id=getattr(self, '_active_session', 'default'),
                image_provider=image_provider,
                time_image_gen=(
                    (_settings.get('_metric_time_llm_prompt') or 0)
                    + (_settings.get('_metric_time_image_gen') or 0)
                ) or None,
            )
            model_result, rec = await self._run_3d_generation(
                generation_mode, api_provider, local_model,
                selected_image_path, multiview_paths, rec=rec,
            )
            if 'error' in model_result:
                raise Exception(model_result['error'])

            model_path = model_result['model_path']
            logger.info(f"3D model generated: {model_path}")

            # ── Step 3: post-processing ────────────────────────────────────
            user_prefs = {
                'auto_orient': auto_orient,
                'generate_supports': generate_supports,
                'max_overhang_angle': max_overhang_angle,
                'make_overhangs_printable': make_overhangs_printable,
                'overhang_printable_angle': overhang_printable_angle,
                'overhang_printable_holes': overhang_printable_holes,
                'overhang_method': overhang_method,
            }
            _t_post = time.perf_counter()
            result_tuple = await self._postprocess_and_return(
                model_path, enable_intelligent_processing,
                llm_provider, llm_model,
                fallback_preview=selected_image_path,
                multiview_paths=multiview_paths,
                user_preferences=user_prefs,
            )
            rec.time_postprocess = time.perf_counter() - _t_post
            rec.time_total = time.perf_counter() - _t_total
            try:
                save_record(rec)
            except Exception as _me:
                logger.warning(f"Could not save metrics: {_me}")
            return result_tuple

        except Exception as e:
            logger.error(f"3D generation error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return (
                [],
                None,
                gr.update(choices=[], value=None),
                f"*Ошибка: {str(e)}*",
                "",
                {},
                None,
                None,
                None,
                "*Сравнение до/после пока недоступно*",
                f"❌ Ошибка: {str(e)}",
            )

    async def handle_continue_to_3d(
        self,
        session_id: str,
        generation_mode: str,
        api_provider: str,
        local_model: str,
        llm_provider: str,
        llm_model: str,
        enable_intelligent_processing: bool,
        auto_orient: bool,
        generate_supports: bool,
        max_overhang_angle: float,
        make_overhangs_printable: bool = False,
        overhang_printable_angle: float = 55.0,
        overhang_printable_holes: float = 0.0,
        overhang_method: str = "voxel",
    ):
        """Continue from multiview gallery to 3D model generation."""
        self.set_active_session(session_id)
        self.update_ui_setting('generation_mode', generation_mode)
        self.update_ui_setting('api_provider', api_provider)
        self.update_ui_setting('local_model', local_model)
        self.update_ui_setting('llm_provider', llm_provider)
        self.update_ui_setting('llm_model', llm_model)
        self.update_ui_setting('enable_intelligent_processing', enable_intelligent_processing)
        self.update_ui_setting('auto_orient', auto_orient)
        self.update_ui_setting('generate_supports', generate_supports)
        self.update_ui_setting('max_overhang_angle', max_overhang_angle)
        self.update_ui_setting('make_overhangs_printable', make_overhangs_printable)
        self.update_ui_setting('overhang_printable_angle', overhang_printable_angle)
        self.update_ui_setting('overhang_printable_holes', overhang_printable_holes)
        self.update_ui_setting('overhang_method', overhang_method)

        if not self.multiview_images:
            return (
                None, gr.update(choices=[], value=None),
                "*Нет multiview изображений*", "", {},
                None, None, None,
                "*Сравнение появится после генерации 3D модели*",
                "⚠️ Сначала сгенерируйте multi-view виды",
            )

        try:
            logger.info("Continuing from multiview to 3D generation...")

            from utils.metrics_collector import GenerationRecord, save_record
            _t_total = time.perf_counter()
            _settings = self.ui_settings
            rec = GenerationRecord(
                session_id=getattr(self, '_active_session', 'default'),
                image_provider=local_model,
                time_image_gen=(
                    (_settings.get('_metric_time_llm_prompt') or 0)
                    + (_settings.get('_metric_time_image_gen') or 0)
                ) or None,
            )
            model_result, rec = await self._run_3d_generation(
                generation_mode, api_provider, local_model,
                image_path=self.multiview_images[0],
                multiview_paths=self.multiview_images,
                rec=rec,
            )
            if 'error' in model_result:
                raise Exception(model_result['error'])

            model_path = model_result['model_path']
            logger.info(f"3D model generated: {model_path}")

            user_prefs = {
                'auto_orient': auto_orient,
                'generate_supports': generate_supports,
                'max_overhang_angle': max_overhang_angle,
                'make_overhangs_printable': make_overhangs_printable,
                'overhang_printable_angle': overhang_printable_angle,
                'overhang_printable_holes': overhang_printable_holes,
                'overhang_method': overhang_method,
            }
            _t_post = time.perf_counter()
            result = await self._postprocess_and_return(
                model_path, enable_intelligent_processing,
                llm_provider, llm_model,
                fallback_preview=self.multiview_images[0] if self.multiview_images else None,
                multiview_paths=None,
                user_preferences=user_prefs,
            )
            rec.time_postprocess = time.perf_counter() - _t_post
            rec.time_total = time.perf_counter() - _t_total
            try:
                save_record(rec)
            except Exception as _me:
                logger.warning(f"Could not save metrics: {_me}")
            # Strip the leading multiview_gallery element — continue_to_3d outputs one fewer value.
            return result[1:]

        except Exception as e:
            logger.error(f"3D generation from multiview error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return (
                None,
                gr.update(choices=[], value=None),
                f"*Ошибка: {str(e)}*",
                "",
                {},
                None,
                None,
                None,
                "*Сравнение до/после пока недоступно*",
                f"❌ Ошибка: {str(e)}",
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_3d_generation(self, generation_mode, api_provider, local_model, image_path, multiview_paths, rec=None):
        # bool() fixes "[] and ..." returning [] instead of False
        use_multiview = bool(multiview_paths and len(multiview_paths) > 1)

        # ── Metrics setup ────────────────────────────────────────────────
        from utils.metrics_collector import GenerationRecord, ResourceSampler, get_vram_gb
        from utils.mesh_analyzer import analyze_mesh

        if rec is None:
            rec = GenerationRecord(session_id=getattr(self, '_active_session', 'default'))
        rec.use_multiview = use_multiview

        sampler = ResourceSampler()
        sampler.start()
        t0 = time.perf_counter()

        try:
            if generation_mode == "Локальная модель":
                effective_model = "hunyuan3d-mv" if use_multiview else local_model
                rec.model_name = effective_model
                rec.image_provider = getattr(self, '_ui_settings', {}).get('image_provider', 'local')
                logger.info(f"Using local model: {effective_model} (multiview={use_multiview})")
                from api_clients.local_3d_client import Local3DClient
                client = Local3DClient(model_name=effective_model, config=self.config)
                if use_multiview:
                    result = await client.generate_from_multiview(image_paths=multiview_paths)
                else:
                    result = await client.generate_from_image(image_path=image_path)
            else:
                rec.model_name = f"api:{api_provider}"
                rec.image_provider = api_provider
                logger.info(f"Using API provider: {api_provider}")
                if use_multiview:
                    result = await self.coordinator.gen_3d_client.generate_from_multiview(image_paths=multiview_paths)
                else:
                    result = await self.coordinator.gen_3d_client.generate_from_image(image_path=image_path)

        finally:
            rec.time_3d_gen = time.perf_counter() - t0
            # sampler.stop() blocks up to 3s — run in thread to not block event loop
            res_stats = await asyncio.get_event_loop().run_in_executor(None, sampler.stop)
            rec.peak_cpu_pct = res_stats["peak_cpu_pct"]
            rec.avg_cpu_pct  = res_stats["avg_cpu_pct"]
            rec.peak_ram_gb  = res_stats["peak_ram_gb"]
            rec.peak_vram_gb = await get_vram_gb()

        # ── Mesh analysis (run in thread — trimesh can be slow on large files) ──
        if result and 'model_path' in result:
            model_path = result['model_path']
            rec.output_file = model_path
            try:
                mesh = await asyncio.get_event_loop().run_in_executor(
                    None, analyze_mesh, model_path
                )
                if not mesh.error:
                    rec.face_count           = mesh.face_count
                    rec.vertex_count         = mesh.vertex_count
                    rec.surface_area_cm2     = mesh.surface_area_cm2
                    rec.total_volume_cm3     = mesh.total_volume_cm3
                    rec.char_size_cm         = mesh.char_size_cm
                    rec.edge_length_total_cm = mesh.edge_length_total_cm
                    rec.cavity_volume_cm3    = mesh.cavity_volume_cm3
                    rec.gci_surface          = mesh.gci_surface
                    rec.gci_topology         = mesh.gci_topology
                    rec.gci_cavity           = mesh.gci_cavity
                    rec.gci_total            = mesh.gci_total
                    rec.is_manifold          = mesh.is_manifold
                    rec.non_manifold_edges   = mesh.non_manifold_edges
                    rec.component_count      = mesh.component_count
                    rec.file_size_mb         = mesh.file_size_mb
                    logger.info(
                        f"Mesh metrics: faces={mesh.face_count}, GCI={mesh.gci_total:.4f} "
                        f"({mesh.gci_category}), manifold={mesh.is_manifold}"
                    )
                    # Attach GCI info to result for display
                    if isinstance(result, dict):
                        result.setdefault('metadata', {}).update({
                            'GCI': round(mesh.gci_total, 4),
                            'GCI категория': mesh.gci_category,
                            'MAE прогноз (мм)': round(mesh.predicted_mae_mm, 3),
                            'Полигонов': mesh.face_count,
                            'Manifold': mesh.is_manifold,
                        })
                else:
                    logger.warning(f"Mesh analysis skipped: {mesh.error}")
            except Exception as e:
                logger.warning(f"Mesh analysis failed: {e}")

        # rec is returned to caller who will add postprocess/total time and save
        return result, rec

    async def _postprocess_and_return(
        self, model_path, enable_intelligent_processing,
        llm_provider, llm_model, fallback_preview, multiview_paths,
        user_preferences=None,
    ):
        from ui.helpers import create_llm_client, format_analysis, get_printable_compare_payload

        if enable_intelligent_processing:
            logger.info(f"Post-processing 3D model... (LLM: {llm_provider}/{llm_model})")
            from agents.autogen.postprocessing_agent import process_model_intelligently
            llm_client = create_llm_client(llm_provider, llm_model, self.coordinator)
            processing_result = await process_model_intelligently(
                input_file=model_path,
                object_name="generated_object",
                orientation_config=self.config.get('orientation_analysis', {}),
                llm_client=llm_client,
                user_preferences=user_preferences or {},
            )
            self.generated_models = [processing_result]
            self.selected_model_index = 0
            compare_before, compare_after, compare_heatmap, compare_info = get_printable_compare_payload(processing_result)
            return (
                multiview_paths or [],
                processing_result['model_file'],
                gr.update(choices=[('generated_object', 0)], value=0),
                format_analysis(processing_result.get('analysis')),
                processing_result.get('reasoning', ''),
                processing_result.get('metadata', {}),
                compare_before,
                compare_after,
                compare_heatmap,
                compare_info,
                "✅ 3D модель успешно сгенерирована и обработана!",
            )
        else:
            result = {
                'object_name': 'generated_object',
                'source_model_file': model_path,
                'model_file': model_path,
                'metadata': {},
                'comparison': {
                    'before_model_file': model_path,
                    'after_model_file': model_path,
                    'heatmap_model_file': None,
                    'heatmap_stats': {},
                },
            }
            self.generated_models = [result]
            self.selected_model_index = 0
            compare_before, compare_after, compare_heatmap, compare_info = get_printable_compare_payload(result)
            return (
                multiview_paths or [],
                model_path,
                gr.update(choices=[('generated_object', 0)], value=0),
                "*Постобработка отключена*",
                "",
                {},
                compare_before,
                compare_after,
                compare_heatmap,
                compare_info,
                "✅ 3D модель успешно сгенерирована!",
            )

    # ------------------------------------------------------------------
    # Legacy: full scene generation from chat
    # ------------------------------------------------------------------

    async def generate_scene(
        self,
        chat_history,
        enable_2d_preview,
        image_provider,
        api_provider,
        use_image_to_3d,
        enable_intelligent_processing,
        auto_orient,
        generate_supports,
        max_overhang_angle,
        session_id: str | None = None,
    ):
        """Execute full generation workflow (legacy chat-based pipeline)."""
        from ui.helpers import format_analysis

        if session_id is not None:
            self.set_active_session(session_id)

        try:
            logger.info("Starting scene generation...")
            scene_plan = await self.coordinator.get_scene_plan(chat_history)

            if not scene_plan:
                return (
                    [], None, [], "*Модели не сгенерированы*", "", {},
                    None, None, None,
                    "*Сравнение до/после пока недоступно*",
                    "⚠️ Нет корректного плана сцены. Пожалуйста, опишите что вы хотите создать в чате.",
                )

            cfg = {
                'image_generation': {
                    'enabled': enable_2d_preview,
                    'provider': image_provider,
                    'style': 'realistic 3D render, product design',
                },
                'use_image_to_3d': use_image_to_3d and enable_2d_preview,
                'postprocessing': {
                    'enabled': enable_intelligent_processing,
                    'auto_orient': auto_orient,
                    'generate_supports': generate_supports,
                    'max_overhang_angle': max_overhang_angle,
                },
            }

            results = await self.coordinator.execute_generation(
                scene_plan, cfg, generate_previews=enable_2d_preview,
            )
            self.generated_models = results
            self.selected_model_index = 0 if results else None

            preview_images, model_choices = [], []
            for i, result in enumerate(results):
                if 'error' in result:
                    continue
                if result.get('2d_preview'):
                    preview_images.append(result['2d_preview'])
                if 'model_file' in result:
                    model_choices.append((result['object_name'], i))

            first = results[0] if results else {}
            first_model = first.get('model_file')
            first_analysis = format_analysis(first.get('analysis'))
            first_reasoning = first.get('reasoning', '')
            first_metadata = first.get('metadata', {})
            from ui.helpers import get_printable_compare_payload
            compare_before, compare_after, compare_heatmap, compare_info = get_printable_compare_payload(first)

            logger.info(f"Returning {len(preview_images)} previews, {len(model_choices)} models")
            return (
                preview_images,
                first_model,
                gr.Dropdown(choices=model_choices, value=0 if model_choices else None),
                first_analysis,
                first_reasoning,
                first_metadata,
                compare_before,
                compare_after,
                compare_heatmap,
                compare_info,
                f"✅ Успешно сгенерировано {len(results)} моделей!",
            )

        except Exception as e:
            import traceback
            logger.error(f"Generation error: {e}\n{traceback.format_exc()}")
            return (
                [], None, gr.Dropdown(choices=[]),
                f"*Error: {str(e)}*", "", {}, None, None, None,
                "*Сравнение до/после пока недоступно*",
                f"❌ Error: {str(e)}",
            )
