"""
Utilities for interactive before/after mesh comparison.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np
import trimesh
from matplotlib import cm
from scipy.spatial import cKDTree

from utils.logger import get_logger

logger = get_logger(__name__)


def _as_mesh(loaded) -> trimesh.Trimesh:
    """Convert trimesh.Scene or mesh-like object into a single Trimesh."""
    if isinstance(loaded, trimesh.Trimesh):
        return loaded

    if isinstance(loaded, trimesh.Scene):
        geometries = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not geometries:
            raise ValueError("Scene does not contain mesh geometry")
        return trimesh.util.concatenate(geometries)

    raise TypeError(f"Unsupported mesh type: {type(loaded)!r}")


def _estimate_rigid_alignment(
    before_mesh: trimesh.Trimesh,
    after_mesh: trimesh.Trimesh,
    sample_count: int,
) -> tuple[np.ndarray, float, str, float]:
    """Estimate transform that maps `after_mesh` points to `before_mesh`."""
    sample_count = int(max(2_000, sample_count))
    before_points, _ = trimesh.sample.sample_surface(before_mesh, sample_count)
    after_points, _ = trimesh.sample.sample_surface(after_mesh, sample_count)

    ext_before = np.maximum(before_mesh.extents, 1e-12)
    ext_after = np.maximum(after_mesh.extents, 1e-12)
    extent_ratio = float(np.median(ext_after / ext_before))
    needs_scale_alignment = extent_ratio < 0.67 or extent_ratio > 1.5

    initial = np.eye(4)
    initial[:3, 3] = before_mesh.centroid - after_mesh.centroid

    if needs_scale_alignment:
        transform, _, cost = trimesh.registration.procrustes(
            after_points,
            before_points,
            reflection=False,
            translation=True,
            scale=True,
            return_cost=True,
        )
        scale = float(np.cbrt(abs(np.linalg.det(transform[:3, :3]))))
        return transform, float(cost), "procrustes_scale", scale

    transform, _, cost = trimesh.registration.icp(
        after_points,
        before_points,
        initial=initial,
        max_iterations=40,
        threshold=1e-7,
        scale=False,
        reflection=False,
    )
    scale = float(np.cbrt(abs(np.linalg.det(transform[:3, :3]))))
    return transform, float(cost), "icp_rigid", scale


def _surface_distance(
    reference_mesh: trimesh.Trimesh,
    query_points: np.ndarray,
    chunk_size: int,
) -> np.ndarray:
    """Distance from query points to reference mesh surface."""
    chunk_size = int(max(2_000, chunk_size))
    n = int(len(query_points))

    try:
        # closest_point may allocate large temporary arrays; process in chunks
        # to avoid OOM on large meshes.
        out = np.empty(n, dtype=float)
        for start in range(0, n, chunk_size):
            end = min(start + chunk_size, n)
            _, distances, _ = trimesh.proximity.closest_point(reference_mesh, query_points[start:end])
            out[start:end] = np.asarray(distances, dtype=float)
        return out
    except Exception:
        # Fallback: nearest reference vertex (less accurate but robust).
        ref_vertices = np.asarray(reference_mesh.vertices)
        tree = cKDTree(ref_vertices)
        out = np.empty(n, dtype=float)
        for start in range(0, n, chunk_size):
            end = min(start + chunk_size, n)
            distances, _ = tree.query(query_points[start:end], k=1)
            out[start:end] = np.asarray(distances, dtype=float)
        return out


def generate_mesh_delta_heatmap(
    before_model_file: str,
    after_model_file: str,
    output_file: Optional[str] = None,
    sample_points: int = 8_000,
    distance_chunk_size: int = 12_000,
) -> Dict:
    """
    Build a colorized GLB heatmap where vertex color encodes change magnitude.

    Distances are computed from each vertex of the processed model (after)
    to the closest surface point of the source model (before), after rigid
    alignment (rotation + translation only).
    """
    sample_points = int(np.clip(sample_points, 2_000, 20_000))
    distance_chunk_size = int(max(2_000, distance_chunk_size))

    before_loaded = trimesh.load(before_model_file, force="mesh")
    after_loaded = trimesh.load(after_model_file, force="mesh")

    before_mesh = _as_mesh(before_loaded)
    after_mesh = _as_mesh(after_loaded)

    if len(before_mesh.vertices) == 0 or len(after_mesh.vertices) == 0:
        raise ValueError("Cannot compare empty meshes")

    transform = np.eye(4)
    icp_cost = 0.0
    alignment_method = "identity"
    alignment_scale = 1.0
    try:
        transform, icp_cost, alignment_method, alignment_scale = _estimate_rigid_alignment(
            before_mesh,
            after_mesh,
            sample_count=sample_points,
        )
    except Exception as exc:
        logger.warning(f"Rigid alignment failed, using identity transform: {exc}")

    aligned_after = after_mesh.copy()
    aligned_after.apply_transform(transform)

    after_vertices_aligned = np.asarray(aligned_after.vertices)
    distances = _surface_distance(
        before_mesh,
        after_vertices_aligned,
        chunk_size=distance_chunk_size,
    )
    distances = np.asarray(np.nan_to_num(distances, nan=0.0, posinf=0.0, neginf=0.0), dtype=float)

    min_d = float(np.min(distances))
    max_d = float(np.max(distances))
    p95 = float(np.percentile(distances, 95.0))

    # Stable normalization: anchor at zero and use robust upper bound.
    # This prevents always stretching tiny residuals into full rainbow.
    model_diag = float(np.linalg.norm(before_mesh.extents))
    near_zero = max(model_diag * 1e-3, 1e-6)
    color_scale_max = max(p95, near_zero)

    if max_d <= near_zero:
        norm = np.zeros_like(distances)
    else:
        norm = np.clip(distances / color_scale_max, 0.0, 1.0)

    # RGBA colors in uint8 for GLB export.
    rgba = (cm.turbo(norm) * 255.0).astype(np.uint8)

    heatmap_mesh = after_mesh.copy()
    heatmap_mesh.visual = trimesh.visual.ColorVisuals(mesh=heatmap_mesh, vertex_colors=rgba)

    if output_file is None:
        out = Path(after_model_file)
        output_file = str(out.with_name(f"{out.stem}_delta_heatmap.glb"))

    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    heatmap_mesh.export(str(out_path))

    stats = {
        "min_mm": min_d,
        "mean_mm": float(np.mean(distances)),
        "p95_mm": p95,
        "max_mm": max_d,
        "color_scale_max_mm": color_scale_max,
        "icp_cost": icp_cost,
        "alignment_method": alignment_method,
        "alignment_scale": alignment_scale,
        "num_vertices": int(len(distances)),
    }

    logger.info(
        "Generated mesh delta heatmap: mean=%.4f, p95=%.4f, max=%.4f (%s)",
        stats["mean_mm"],
        stats["p95_mm"],
        stats["max_mm"],
        output_file,
    )

    return {
        "before_model_file": before_model_file,
        "after_model_file": after_model_file,
        "heatmap_model_file": str(out_path),
        "heatmap_stats": stats,
    }
