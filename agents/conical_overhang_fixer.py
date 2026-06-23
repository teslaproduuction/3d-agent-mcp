"""
Conical overhang fixer — Python reimplementation of OrcaSlicer's
apply_conical_overhang() from PrintObjectSlice.cpp.

Algorithm:
1. Voxelize the mesh.
2. Process voxel layers top → bottom:
    - Shrink each upper layer in XY by a cone angle dependent radius
   - Union with the current layer
   - Optionally fill small holes in the upper layer first
3. Extract modified mesh via marching cubes.
4. Smooth with Laplacian filter.

The result is a mesh where no overhang exceeds max_angle from horizontal.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import trimesh
from scipy.ndimage import binary_erosion, label, binary_fill_holes

logger = logging.getLogger(__name__)


class ConicalOverhangFixer:
    """
    Makes overhangs printable by applying a conical geometry modification.

    Parameters
    ----------
    layer_height : float
        Z-resolution for voxelization in mm (= typical printer layer height).
    max_angle : float
        Maximum allowed overhang angle from horizontal in degrees.
        0° → entire model becomes a cone/pyramid (maximum modification).
        55° (OrcaSlicer default) → only steep overhangs > 55° are fixed.
        90° → no modification.
    max_hole_area : float
        Maximum area of holes (mm²) in each layer that will be filled before
        applying the conical expansion.  0 = do not fill holes.
    smooth_iterations : int
        Number of Laplacian smoothing passes to reduce voxel staircase artifacts.
    """

    def __init__(
        self,
        layer_height: float = 0.2,
        max_angle: float = 55.0,
        max_hole_area: float = 0.0,
        smooth_iterations: int = 10,
    ):
        self.layer_height = layer_height
        self.max_angle = max_angle
        self.max_hole_area = max_hole_area
        self.smooth_iterations = smooth_iterations

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fix(self, mesh: trimesh.Trimesh, method: str = "voxel") -> trimesh.Trimesh:
        """
        Apply conical overhang fix and return the modified mesh.

        Parameters
        ----------
        method : str
            "voxel"  — voxelization + marching cubes (robust, loses fine detail)
            "vertex" — per-vertex displacement (preserves topology & detail,
                       may leave minor overhangs on concave surfaces)

        The returned mesh is placed with its lowest point at Z = 0.
        """
        if method == "vertex":
            return self._fix_vertex(mesh)
        # default: voxel
        if self.max_angle >= 89.9:
            logger.info("ConicalOverhangFixer: max_angle >= 90°, no modification needed")
            return mesh.copy()

        logger.info(
            f"ConicalOverhangFixer: voxelizing at pitch={self.layer_height}mm, "
            f"max_angle={self.max_angle}°"
        )

        # Some generators output normalized meshes (units close to 1.0), while
        # layer_height is configured in print-like mm units. Keep enough voxels
        # across model extent to avoid collapsing geometry into a coarse blob.
        bounds = mesh.bounds
        extents = np.maximum(bounds[1] - bounds[0], 1e-9)
        min_extent = float(np.min(extents))
        # Higher resolution = better quality. 256 gives ~4x detail vs old 96.
        # Cap at 384 to avoid OOM on large meshes.
        target_min_voxels = min(384.0, max(256.0, float(len(mesh.vertices)) ** 0.35))
        adaptive_pitch = min_extent / target_min_voxels
        effective_pitch = float(min(self.layer_height, adaptive_pitch))
        effective_pitch = max(effective_pitch, self.layer_height / 32.0)

        # Voxelize
        try:
            voxels = mesh.voxelized(pitch=effective_pitch)
            voxels = voxels.fill()          # fill interior voids
        except Exception as exc:
            logger.error(f"Voxelization failed: {exc}")
            return mesh.copy()

        matrix = np.array(voxels.matrix, dtype=bool)  # shape (X, Y, Z)

        if matrix.sum() == 0:
            logger.warning("ConicalOverhangFixer: empty voxel matrix, returning original")
            return mesh.copy()

        # Orca-like shrink radius in XY for each one-layer Z step.
        # In isotropic voxel space this is tan(angle) voxels and avoids mixing
        # print-mm units with mesh units.
        offset_voxels = int(np.ceil(np.tan(np.radians(self.max_angle))))

        # Circular footprint approximates polygon offset better than the default
        # cross-shaped iterative dilation and avoids boxy artifacts.
        footprint = None
        if offset_voxels > 0:
            radius = offset_voxels
            yy, xx = np.ogrid[-radius: radius + 1, -radius: radius + 1]
            footprint = (xx * xx + yy * yy) <= (radius * radius)

        # Max hole size in voxels²
        max_hole_pixels = 0
        if self.max_hole_area > 0:
            max_hole_pixels = int(self.max_hole_area / (effective_pitch ** 2))

        n_z = matrix.shape[2]
        logger.info(
            f"Matrix shape: {matrix.shape}, effective_pitch={effective_pitch:.5f}, "
            f"offset_voxels={offset_voxels}, n_layers={n_z}"
        )

        # Process top → bottom
        for z in range(n_z - 2, -1, -1):
            upper = matrix[:, :, z + 1].copy()

            # Fill small holes in upper layer
            if max_hole_pixels > 0:
                upper = self._fill_small_holes(upper, max_hole_pixels)

            # Shrink upper layer in XY (Orca offset with negative sign).
            if offset_voxels > 0 and footprint is not None:
                # If the kernel is larger than the layer span, erosion is empty.
                if (2 * offset_voxels + 1) > min(upper.shape):
                    expanded = np.zeros_like(upper)
                else:
                    expanded = binary_erosion(
                        upper,
                        structure=footprint,
                        iterations=1,
                        border_value=0,
                    )
            else:
                expanded = upper

            # Union with current layer
            matrix[:, :, z] |= expanded

        # Rebuild voxel grid with same transform
        try:
            new_voxels = trimesh.voxel.VoxelGrid(matrix, transform=voxels.transform)
            result_mesh = new_voxels.marching_cubes
            # trimesh returns marching-cubes vertices in voxel index space.
            # Apply the voxel transform explicitly to preserve original scale.
            result_mesh.apply_transform(voxels.transform)
        except Exception as exc:
            logger.error(f"Marching cubes failed: {exc}")
            return mesh.copy()

        # Smooth staircase artifacts — Taubin preserves volume better than Laplacian.
        if self.smooth_iterations > 0 and len(result_mesh.vertices) > 0:
            try:
                trimesh.smoothing.filter_taubin(
                    result_mesh,
                    iterations=self.smooth_iterations,
                    lamb=0.5,
                    nu=-0.53,
                )
            except Exception as exc:
                logger.debug(f"Smoothing failed (non-critical): {exc}")

        # Decimate back toward original face count to avoid polygon explosion.
        # Marching cubes on high-res grid produces 5-10x more faces than original.
        original_faces = len(mesh.faces)
        if len(result_mesh.faces) > original_faces * 1.5:
            try:
                target = max(original_faces, int(len(result_mesh.faces) * 0.4))
                result_mesh = result_mesh.simplify_quadric_decimation(target)
                logger.info(f"Decimated to {len(result_mesh.faces)} faces (target {target})")
            except Exception as exc:
                logger.debug(f"Decimation failed (non-critical): {exc}")

        # Place on bed
        if len(result_mesh.vertices) > 0:
            min_z = result_mesh.bounds[0][2]
            result_mesh.apply_translation([0, 0, -min_z])

        logger.info(
            f"ConicalOverhangFixer: done. "
            f"Vertices: {len(mesh.vertices)} → {len(result_mesh.vertices)}, "
            f"Faces: {len(mesh.faces)} → {len(result_mesh.faces)}"
        )
        return result_mesh

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fix_vertex(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """
        Per-vertex displacement approach.

        For every vertex that creates an overhang beyond max_angle, slide it
        horizontally (in XY) inward so it falls within the allowed cone defined
        by the vertex directly below it.

        Algorithm (iterative, bottom-up):
        1. Sort vertices by Z ascending.
        2. For each vertex, find the nearest vertex below it (within xy_radius).
        3. Compute max allowed XY offset: dz * tan(max_angle).
        4. If current XY offset exceeds that, clamp it.
        5. Repeat passes until convergence (max 8 passes).

        Preserves exact face count and topology. Only vertex positions change.
        """
        if self.max_angle >= 89.9:
            return mesh.copy()

        result = mesh.copy()
        verts = result.vertices.copy()  # (N, 3)
        tan_angle = np.tan(np.radians(self.max_angle))

        # Bottom-up sort index
        z_order = np.argsort(verts[:, 2])

        max_passes = 8
        for pass_idx in range(max_passes):
            moved = 0
            for i in z_order:
                # Find vertices below this one
                z_i = verts[i, 2]
                below_mask = verts[:, 2] < z_i - 1e-6
                if not below_mask.any():
                    continue

                below_idx = np.where(below_mask)[0]
                below_verts = verts[below_idx]

                # XY distances to all vertices below
                dxy = below_verts[:, :2] - verts[i, :2]
                dxy_dist = np.linalg.norm(dxy, axis=1)
                dz = z_i - below_verts[:, 2]

                # Allowed XY offset from each support vertex
                allowed_r = dz * tan_angle

                # Vertices that could support this one (within cone)
                in_cone = dxy_dist <= allowed_r + 1e-6

                if in_cone.any():
                    # Already supported — no move needed
                    continue

                # Find closest vertex below as anchor
                anchor_local = np.argmin(dxy_dist)
                anchor_z = below_verts[anchor_local, 2]
                anchor_xy = below_verts[anchor_local, :2]
                dz_anchor = z_i - anchor_z
                max_r = dz_anchor * tan_angle

                # Current XY offset from anchor
                cur_vec = verts[i, :2] - anchor_xy
                cur_r = np.linalg.norm(cur_vec)

                if cur_r > max_r + 1e-6 and cur_r > 1e-9:
                    # Clamp to cone surface
                    verts[i, :2] = anchor_xy + cur_vec / cur_r * max_r
                    moved += 1

            logger.debug(f"Vertex pass {pass_idx + 1}: moved {moved} vertices")
            if moved == 0:
                break

        result.vertices = verts

        # Light smoothing to reduce kinks at displaced vertices
        if self.smooth_iterations > 0:
            try:
                trimesh.smoothing.filter_taubin(
                    result,
                    iterations=min(self.smooth_iterations, 5),
                    lamb=0.3,
                    nu=-0.32,
                )
            except Exception as exc:
                logger.debug(f"Vertex smooth failed (non-critical): {exc}")

        # Place on bed
        if len(result.vertices) > 0:
            min_z = result.bounds[0][2]
            result.apply_translation([0, 0, -min_z])

        logger.info(
            f"ConicalOverhangFixer (vertex): done. "
            f"Vertices: {len(mesh.vertices)} (unchanged), "
            f"Faces: {len(mesh.faces)} (unchanged)"
        )
        return result

    @staticmethod
    def _fill_small_holes(layer: np.ndarray, max_hole_pixels: int) -> np.ndarray:
        """
        Fill small enclosed holes (voids) in a 2D binary layer.

        Holes with area <= max_hole_pixels are filled.
        Larger holes are preserved (they are intentional design features).
        """
        # Find the inverse (holes = regions NOT occupied that are enclosed)
        filled = binary_fill_holes(layer)
        holes = filled & ~layer  # regions that were filled = enclosed holes

        if not holes.any():
            return layer

        # Label individual hole regions
        labeled, n_holes = label(holes)
        result = layer.copy()

        for hole_id in range(1, n_holes + 1):
            hole_mask = labeled == hole_id
            hole_size = int(hole_mask.sum())
            if hole_size <= max_hole_pixels:
                result |= hole_mask   # fill this small hole

        return result

    # ------------------------------------------------------------------
    # Analysis helper (does not modify mesh)
    # ------------------------------------------------------------------

    def analyze_overhangs(self, mesh: trimesh.Trimesh, overhang_angle: float = 45.0) -> dict:
        """
        Analyze overhang statistics of a mesh without modifying it.

        Returns dict with keys: overhang_area_mm2, overhang_face_count,
        max_overhang_angle_deg, needs_fix.
        """
        face_normals = mesh.face_normals
        face_areas = mesh.area_faces
        nz = face_normals[:, 2]

        # Overhang: faces pointing downward past threshold
        threshold_cos = np.cos(np.pi - overhang_angle * np.pi / 180.0)
        overhang_mask = nz < threshold_cos

        overhang_area = float(np.sum(face_areas[overhang_mask]))
        overhang_count = int(overhang_mask.sum())

        # Steepest overhang angle
        downward_mask = nz < 0
        if downward_mask.any():
            min_nz = float(np.min(nz[downward_mask]))
            max_overhang_deg = float(np.degrees(np.arccos(np.clip(-min_nz, 0, 1))))
        else:
            max_overhang_deg = 0.0

        return {
            "overhang_area_mm2": overhang_area,
            "overhang_face_count": overhang_count,
            "max_overhang_angle_deg": max_overhang_deg,
            "needs_fix": overhang_area > 0.1,
        }
