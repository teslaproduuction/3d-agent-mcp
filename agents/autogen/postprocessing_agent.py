"""
AutoGen PostProcessing Agent with enhanced orientation analysis
Uses AssistantAgent with EnhancedOrientationAnalyzer
"""
import asyncio
import os

from autogen import AssistantAgent
from typing import List, Dict
import trimesh
from pathlib import Path
from dataclasses import asdict

from agents.enhanced_orientation_analyzer import EnhancedOrientationAnalyzer, metrics_to_dict
from agents.orca_orientation_analyzer import OrcaOrientationAnalyzer
from agents.conical_overhang_fixer import ConicalOverhangFixer
from api_clients.llm_client import LLMClient
from utils.logger import get_logger
from utils.mesh_compare import generate_mesh_delta_heatmap

logger = get_logger(__name__)


def _run_orca_orientation(mesh, critical_angle: float):
    """Run Orca orientation analysis in a worker thread."""
    orca_analyzer = OrcaOrientationAnalyzer(overhang_angle=critical_angle)
    orca_rot3, orca_cost = orca_analyzer.orient(mesh)
    import numpy as np
    best_transform = np.eye(4)
    best_transform[:3, :3] = orca_rot3
    return best_transform, orca_cost


def _render_mesh_preview(mesh, output_file: str):
    """Render preview image for mesh in a worker thread."""
    scene = mesh.scene()
    png_bytes = scene.save_image(resolution=(512, 512), visible=True)
    if not png_bytes:
        return None

    preview_path = Path(output_file).parent / f"{Path(output_file).stem}_preview.png"
    preview_path.write_bytes(png_bytes)
    return str(preview_path)


POSTPROCESSING_SYSTEM_MESSAGE = """
You are an expert in 3D printing and model preparation.

Your role:
1. Analyze 3D model geometry for printability
2. Optimize orientation for best print quality
3. Recommend support strategies
4. Generate detailed reasoning about processing decisions

You have access to comprehensive analysis data including:
- Multiple orientation tests (24+ options)
- Overhang angles and areas
- Print time estimates
- Support volume estimates
- Layer quality scores

Provide clear, actionable recommendations for each model.
"""


def create_postprocessing_agent(
    config_list: List[Dict],
    llm_client: LLMClient,
    orientation_config: Dict,
    **kwargs
) -> AssistantAgent:
    """
    Create AutoGen PostProcessing Agent

    Args:
        config_list: List of LLM configurations
        llm_client: LLM client for reasoning generation
        orientation_config: Configuration for orientation analysis
        **kwargs: Additional arguments for AssistantAgent

    Returns:
        AssistantAgent configured for postprocessing
    """
    logger.info("Creating AutoGen PostProcessing Agent")

    agent = AssistantAgent(
        name="postprocessor",
        system_message=POSTPROCESSING_SYSTEM_MESSAGE,
        llm_config={
            "config_list": config_list,
            "temperature": 0.5,
            "timeout": 120,
        },
        human_input_mode="NEVER",
        max_consecutive_auto_reply=5,
        **kwargs
    )

    # Store configuration as attribute
    agent.orientation_config = orientation_config
    agent.llm_client = llm_client

    logger.info("PostProcessing Agent created successfully")
    return agent


async def process_model_intelligently(
    input_file: str,
    object_name: str,
    orientation_config: Dict,
    llm_client: LLMClient = None,
    output_file: str = None,
    user_preferences: Dict = None,
) -> Dict:
    """
    Process 3D model with enhanced orientation analysis

    Args:
        input_file: Path to input GLB/STL file
        object_name: Name of the object
        orientation_config: Configuration for orientation analysis
        llm_client: Optional LLM client for reasoning
        output_file: Optional output path

    Returns:
        Dict with processed model info and analysis
    """
    logger.info(f"Starting intelligent processing for: {object_name}")
    if user_preferences is None:
        user_preferences = {}

    if output_file is None:
        input_path = Path(input_file)
        output_file = str(input_path.parent / f"{input_path.stem}_printable.stl")

    source_model_file = input_file

    # Load mesh
    mesh = await asyncio.to_thread(trimesh.load, input_file, force='mesh')
    logger.info(f"Loaded mesh: {len(mesh.faces)} faces")

    # ── Orientation ────────────────────────────────────────────────────────
    use_orca = user_preferences.get('auto_orient', True)
    critical_angle = float(user_preferences.get('max_overhang_angle', 45.0))

    if use_orca:
        try:
            best_transform, orca_cost = await asyncio.to_thread(
                _run_orca_orientation,
                mesh,
                critical_angle,
            )
            logger.info(f"OrcaSlicer orientation: unprintability={orca_cost.unprintability:.4f}")
        except Exception as exc:
            logger.warning(f"OrcaSlicer orientation failed, falling back: {exc}")
            use_orca = False

    if not use_orca:
        analyzer = EnhancedOrientationAnalyzer(
            num_orientations=orientation_config.get('num_orientations', 24),
            critical_angle=critical_angle,
            layer_height=orientation_config.get('layer_height', 0.2),
            print_speed=orientation_config.get('print_speed', 50.0),
            scoring_weights=orientation_config.get('scoring_weights', {})
        )
        best_transform, _ = await asyncio.to_thread(analyzer.analyze_all_orientations, mesh)

    # Compute metrics for reporting (always use EnhancedOrientationAnalyzer)
    reporting_analyzer = EnhancedOrientationAnalyzer(
        num_orientations=6,
        critical_angle=critical_angle,
        layer_height=orientation_config.get('layer_height', 0.2),
        print_speed=orientation_config.get('print_speed', 50.0),
    )
    _, all_metrics = await asyncio.to_thread(reporting_analyzer.analyze_all_orientations, mesh)

    # Apply best orientation
    mesh.apply_transform(best_transform)

    # ── Make overhangs printable (conical fix) ─────────────────────────────
    conical_applied = False
    if user_preferences.get('make_overhangs_printable', False):
        try:
            fixer = ConicalOverhangFixer(
                layer_height=orientation_config.get('layer_height', 0.2),
                max_angle=float(user_preferences.get('overhang_printable_angle', 55.0)),
                max_hole_area=float(user_preferences.get('overhang_printable_holes', 0.0)),
            )
            logger.info("Applying conical overhang fix...")
            fixed = await asyncio.to_thread(fixer.fix, mesh)
            if len(fixed.vertices) > 0:
                mesh = fixed
                conical_applied = True
                logger.info("Conical overhang fix applied successfully")
            else:
                logger.warning("Conical fix produced empty mesh, skipping")
        except Exception as exc:
            logger.warning(f"Conical overhang fix failed: {exc}")

    # Center and place on platform
    mesh.apply_translation(-mesh.center_mass)
    mesh.apply_translation([0, 0, -mesh.bounds[0][2]])

    # Repair mesh if needed
    if not mesh.is_watertight:
        logger.info("Mesh is not watertight, applying repairs...")
        trimesh.repair.fix_normals(mesh)
        trimesh.repair.fill_holes(mesh)
        trimesh.repair.fix_winding(mesh)

    # Export to STL
    await asyncio.to_thread(mesh.export, output_file)
    logger.info(f"Processed model saved to: {output_file}")

    comparison = {
        'before_model_file': source_model_file,
        'after_model_file': output_file,
        'heatmap_model_file': None,
        'heatmap_stats': {},
    }
    heatmap_enabled = os.getenv("HEATMAP_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
    if heatmap_enabled:
        sample_points_raw = os.getenv("HEATMAP_SAMPLE_POINTS", "8000")
        chunk_size_raw = os.getenv("HEATMAP_CHUNK_SIZE", "12000")
        try:
            sample_points = int(sample_points_raw)
        except (TypeError, ValueError):
            sample_points = 8000
        try:
            chunk_size = int(chunk_size_raw)
        except (TypeError, ValueError):
            chunk_size = 12000

        try:
            comparison = await asyncio.to_thread(
                generate_mesh_delta_heatmap,
                source_model_file,
                output_file,
                sample_points=sample_points,
                distance_chunk_size=chunk_size,
            )
        except Exception as exc:
            logger.warning(f"Could not generate mesh delta heatmap: {exc}")
    else:
        logger.info("Heatmap compare disabled by HEATMAP_ENABLED")

    # Convert metrics to dict for JSON serialization
    best_metrics = all_metrics[0]
    all_metrics_dict = [metrics_to_dict(m) for m in all_metrics]

    # Generate reasoning with LLM
    reasoning = ""
    if llm_client:
        try:
            reasoning = await _generate_reasoning(
                llm_client,
                object_name,
                best_metrics,
                all_metrics
            )
        except Exception as e:
            logger.error(f"Failed to generate reasoning: {e}")
            reasoning = f"Processing completed. Best orientation: {best_metrics.rotation_angles}"

    # Build analysis dict expected by UI
    overhang = best_metrics.max_overhang_angle
    if overhang < 30:
        complexity = 'low'
        difficulty = 'easy'
    elif overhang < 45:
        complexity = 'medium'
        difficulty = 'medium'
    else:
        complexity = 'high'
        difficulty = 'hard'

    analysis = {
        'complexity': complexity,
        'print_difficulty': difficulty,
        'max_overhang_angle': float(best_metrics.max_overhang_angle),
        'overhang_area_mm2': float(best_metrics.overhang_area),
        'contact_area_mm2': float(best_metrics.contact_area),
        'has_internal_cavities': not mesh.is_watertight,
        'is_printable_without_supports': overhang < 45.0,
        'recommended_support_strategy': 'none' if overhang < 45.0 else 'tree',
    }

    # Render preview image of the processed STL
    preview_image = None
    try:
        preview_image = await asyncio.to_thread(_render_mesh_preview, mesh, output_file)
        if preview_image:
            logger.info(f"Preview image saved: {preview_image}")
    except Exception as e:
        logger.warning(f"Could not render preview: {e}")

    # Compile results
    result = {
        'object_name': object_name,
        'source_model_file': source_model_file,
        'model_file': output_file,
        'analysis': analysis,
        'preview_image': preview_image,
        'comparison': comparison,
        'best_orientation': {
            'rotation_angles': best_metrics.rotation_angles,
            'transform': best_metrics.transform.tolist(),
            'max_overhang_angle': best_metrics.max_overhang_angle,
            'overhang_area': best_metrics.overhang_area,
            'contact_area': best_metrics.contact_area,
            'estimated_print_time': best_metrics.estimated_print_time,
            'estimated_support_volume': best_metrics.estimated_support_volume,
            'layer_quality_score': best_metrics.layer_quality_score,
            'total_score': best_metrics.total_score
        },
        'all_orientations': all_metrics_dict,
        'num_orientations_tested': len(all_metrics),
        'reasoning': reasoning,
        'metadata': {
            'num_faces': len(mesh.faces),
            'volume_mm3': float(mesh.volume),
            'surface_area_mm2': float(mesh.area),
            'bounding_box_mm': mesh.bounds.tolist(),
            'is_watertight': mesh.is_watertight,
            'conical_fix_applied': conical_applied,
            'conical_fix_angle_deg': float(user_preferences.get('overhang_printable_angle', 55.0)),
        }
    }

    logger.info(f"Processing complete for {object_name}")
    return result


async def _generate_reasoning(
    llm_client: LLMClient,
    object_name: str,
    best_metrics,
    all_metrics: List
) -> str:
    """Generate human-readable reasoning using LLM"""

    # Get top 3 orientations for comparison
    top_3 = all_metrics[:3]

    comparison = "\n".join([
        f"Option {i+1}: angles={m.rotation_angles}, "
        f"overhang={m.max_overhang_angle:.1f}°, "
        f"print_time={m.estimated_print_time:.2f}h, "
        f"score={m.total_score:.2f}"
        for i, m in enumerate(top_3)
    ])

    prompt = f"""
Analyze this 3D printing orientation decision for "{object_name}":

Selected orientation: {best_metrics.rotation_angles}
- Max overhang angle: {best_metrics.max_overhang_angle:.1f}°
- Print time: {best_metrics.estimated_print_time:.2f} hours
- Support volume: {best_metrics.estimated_support_volume:.0f} mm³
- Layer quality: {best_metrics.layer_quality_score:.2f}

Top 3 alternatives tested:
{comparison}

Total orientations tested: {len(all_metrics)}

Write a concise 2-3 sentence explanation of why this orientation is optimal for 3D printing.
Focus on printability, quality, and efficiency.
"""

    response = await llm_client.complete(prompt=prompt, temperature=0.7, max_tokens=500)
    return response
