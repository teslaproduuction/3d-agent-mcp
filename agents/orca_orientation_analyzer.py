"""
OrcaSlicer-style auto-orientation algorithm reimplemented in Python.

Based on OrcaSlicer's Orient.cpp (AutoOrienter class):
- Area accumulation: finds top-N face normals by total area
- 18 standard supplemental orientations
- OrcaSlicer cost function: overhang, bottom area, contour, low-angle faces
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import trimesh

logger = logging.getLogger(__name__)

# OrcaSlicer constants from Orient.cpp
RELATIVE_F = 6.61
TAR_C = 1.0
TAR_D = 0.177
TAR_LAF = 0.1
BOTTOM_F = 1.0
TAR_E = 1.0
CONTOUR_F = 0.1

# Low-angle face range (14° to 90° from horizontal)
LAF_MIN = np.cos(np.radians(14))   # 0.9703
LAF_MAX = np.cos(np.radians(1.4))  # 0.9997

# Standard 18 supplemental orientations from OrcaSlicer
_S = 1.0 / np.sqrt(2)
STANDARD_ORIENTATIONS: List[List[float]] = [
    # 6 axis-aligned
    [0, 0, -1],
    [0, 0, 1],
    [1, 0, 0],
    [-1, 0, 0],
    [0, 1, 0],
    [0, -1, 0],
    # 12 diagonal (45° combinations)
    [_S, 0, -_S],
    [-_S, 0, -_S],
    [0, _S, -_S],
    [0, -_S, -_S],
    [_S, 0, _S],
    [-_S, 0, _S],
    [0, _S, _S],
    [0, -_S, _S],
    [_S, _S, 0],
    [_S, -_S, 0],
    [-_S, _S, 0],
    [-_S, -_S, 0],
]


@dataclass
class OrcaCost:
    overhang: float        # overhang face area penalty
    bottom: float          # bottom contact area (larger = better)
    area_laf: float        # low-angle face area (penalty)
    contour: float         # perimeter proxy of bottom area
    unprintability: float  # final score (lower = better)


def _rotation_from_two_vectors(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Return 3x3 rotation matrix that rotates unit vector src → dst."""
    src = src / (np.linalg.norm(src) + 1e-12)
    dst = dst / (np.linalg.norm(dst) + 1e-12)
    dot = float(np.clip(np.dot(src, dst), -1.0, 1.0))
    if dot > 0.9999999:
        return np.eye(3)
    if dot < -0.9999999:
        # 180° rotation: find perpendicular axis
        perp = np.array([1, 0, 0]) if abs(src[0]) < 0.9 else np.array([0, 1, 0])
        axis = np.cross(src, perp)
        axis /= np.linalg.norm(axis)
        # Rodrigues for 180°
        return 2 * np.outer(axis, axis) - np.eye(3)
    axis = np.cross(src, dst)
    axis /= np.linalg.norm(axis)
    angle = np.arccos(dot)
    K = np.array([
        [0, -axis[2], axis[1]],
        [axis[2], 0, -axis[0]],
        [-axis[1], axis[0], 0],
    ])
    return np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * (K @ K)


class OrcaOrientationAnalyzer:
    """
    Python reimplementation of OrcaSlicer's AutoOrienter.

    Usage:
        analyzer = OrcaOrientationAnalyzer(overhang_angle=30)
        rotation_matrix_3x3 = analyzer.orient(mesh)
    """

    def __init__(self, overhang_angle: float = 30.0, n_top_faces: int = 10):
        """
        Args:
            overhang_angle: threshold angle in degrees (same as OrcaSlicer's support_threshold_angle)
            n_top_faces: number of top face-normal candidates from area accumulation
        """
        self.overhang_angle = overhang_angle
        self.n_top_faces = n_top_faces

    # ------------------------------------------------------------------
    # Candidate generation
    # ------------------------------------------------------------------

    def find_candidate_orientations(self, mesh: trimesh.Trimesh) -> List[np.ndarray]:
        """
        Area accumulation: find top-N face normals by total area.
        Returns candidate "down" vectors (the face that should face the bed).
        """
        face_normals = mesh.face_normals          # (F, 3)
        face_areas = mesh.area_faces               # (F,)

        # Quantize normals to 3 decimal places for grouping
        quantized = np.round(face_normals, 3)

        # Accumulate area per quantized normal
        area_map: dict = {}
        normal_map: dict = {}  # stores the highest-area accurate normal per group
        max_area_map: dict = {}

        for i in range(len(face_normals)):
            key = tuple(quantized[i])
            area = float(face_areas[i])
            area_map[key] = area_map.get(key, 0.0) + area
            if area > max_area_map.get(key, 0.0):
                max_area_map[key] = area
                normal_map[key] = face_normals[i].copy()

        # Sort by total area, take top-N
        sorted_keys = sorted(area_map.keys(), key=lambda k: area_map[k], reverse=True)
        candidates = [normal_map[k] for k in sorted_keys[: self.n_top_faces]]

        # Add 18 standard orientations
        for std in STANDARD_ORIENTATIONS:
            candidates.append(np.array(std, dtype=float))

        # Remove near-duplicates (dot product > 1 - 1e-6)
        candidates = self._remove_duplicates(candidates)
        return candidates

    @staticmethod
    def _remove_duplicates(candidates: List[np.ndarray], tol: float = 1e-4) -> List[np.ndarray]:
        unique: List[np.ndarray] = []
        for c in candidates:
            c_norm = c / (np.linalg.norm(c) + 1e-12)
            is_dup = False
            for u in unique:
                u_norm = u / (np.linalg.norm(u) + 1e-12)
                if abs(float(np.dot(c_norm, u_norm))) > 1.0 - tol:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(c_norm)
        return unique

    # ------------------------------------------------------------------
    # Cost function
    # ------------------------------------------------------------------

    def compute_cost(
        self,
        mesh: trimesh.Trimesh,
        down_normal: np.ndarray,
    ) -> OrcaCost:
        """
        OrcaSlicer cost function for placing `down_normal` facing the bed.

        Rotates mesh normals so that down_normal → -Z (bed direction),
        then computes overhang, bottom, LAF, contour metrics.
        """
        # Build rotation: down_normal → (0, 0, -1)
        rot = _rotation_from_two_vectors(down_normal, np.array([0.0, 0.0, -1.0]))
        rotated_normals = (rot @ mesh.face_normals.T).T   # (F, 3)
        face_areas = mesh.area_faces                       # (F,)

        # ASCENT threshold for this overhang angle
        # Faces with rotated_z < ASCENT are overhangs (pointing downward)
        ascent = np.cos(np.pi - self.overhang_angle * np.pi / 180.0)

        nz = rotated_normals[:, 2]

        # Overhang: faces pointing down past threshold
        overhang_mask = nz < ascent
        overhang = float(np.sum(face_areas[overhang_mask]))

        # Bottom: faces nearly parallel to bed (pointing mostly down, nz < -0.999)
        bottom_mask = nz < -0.999
        bottom = float(np.sum(face_areas[bottom_mask]))

        # Low-angle faces (LAF): pologiye granyey 14°-90° from horizontal
        # These are faces with nz between LAF_MIN and LAF_MAX (nearly horizontal but not flat)
        # In OrcaSlicer: faces whose normal is near-vertical (cos ≈ 1) need supports on gently-sloped surfaces
        laf_mask = (nz > LAF_MIN) & (nz < LAF_MAX)
        area_laf = float(np.sum(face_areas[laf_mask]))

        # Contour proxy: square root of bottom area (approximates perimeter)
        contour = np.sqrt(bottom) if bottom > 0 else 0.0

        # OrcaSlicer cost formula (area-weighted mode)
        denominator = TAR_D + CONTOUR_F * contour + BOTTOM_F * bottom + TAR_E * overhang
        if denominator < 1e-9:
            denominator = 1e-9

        unprintability = RELATIVE_F * (overhang * TAR_C + TAR_D + TAR_LAF * area_laf) / denominator

        return OrcaCost(
            overhang=overhang,
            bottom=bottom,
            area_laf=area_laf,
            contour=contour,
            unprintability=unprintability,
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def orient(self, mesh: trimesh.Trimesh) -> Tuple[np.ndarray, OrcaCost]:
        """
        Find the optimal orientation for 3D printing.

        Returns:
            (rotation_matrix_3x3, best_cost)
            Apply as: mesh.apply_transform(np.eye(4)); mesh.vertices @= rotation_matrix.T
        """
        candidates = self.find_candidate_orientations(mesh)
        logger.info(f"OrcaOrientationAnalyzer: testing {len(candidates)} orientation candidates")

        best_cost: Optional[OrcaCost] = None
        best_rotation = np.eye(3)
        best_normal = np.array([0.0, 0.0, -1.0])

        for normal in candidates:
            try:
                cost = self.compute_cost(mesh, normal)
            except Exception as exc:
                logger.debug(f"Cost computation failed for normal {normal}: {exc}")
                continue

            if best_cost is None or cost.unprintability < best_cost.unprintability:
                best_cost = cost
                best_normal = normal
                best_rotation = _rotation_from_two_vectors(
                    normal, np.array([0.0, 0.0, -1.0])
                )

        if best_cost is None:
            logger.warning("OrcaOrientationAnalyzer: all candidates failed, returning identity")
            best_cost = OrcaCost(0, 0, 0, 0, 0)

        logger.info(
            f"Best orientation: normal={best_normal.round(3)}, "
            f"unprintability={best_cost.unprintability:.4f}, "
            f"overhang={best_cost.overhang:.1f}mm², bottom={best_cost.bottom:.1f}mm²"
        )
        return best_rotation, best_cost

    def orient_and_apply(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """
        Orient mesh and return a new mesh placed on the bed (Z=0).
        """
        rotation_3x3, cost = self.orient(mesh)

        # Build 4x4 transform
        transform = np.eye(4)
        transform[:3, :3] = rotation_3x3

        result = mesh.copy()
        result.apply_transform(transform)

        # Place on bed (Z=0)
        min_z = result.bounds[0][2]
        result.apply_translation([0, 0, -min_z])

        return result
