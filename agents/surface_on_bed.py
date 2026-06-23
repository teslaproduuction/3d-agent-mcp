"""
Surface-on-bed: detect flat face groups and rotate the model to place a chosen
face on the print bed.

Usage:
    mesh = trimesh.load("model.stl")
    groups = detect_flat_faces(mesh)
    new_mesh = apply_face_to_bed(mesh, groups[0].normal, "output.stl")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import trimesh

logger = logging.getLogger(__name__)

# Direction labels (approximate) for human-readable names
_DIRECTION_LABELS = [
    (np.array([0, 0, 1]),  "Верхняя"),
    (np.array([0, 0, -1]), "Нижняя"),
    (np.array([1, 0, 0]),  "Правая"),
    (np.array([-1, 0, 0]), "Левая"),
    (np.array([0, 1, 0]),  "Передняя"),
    (np.array([0, -1, 0]), "Задняя"),
]


@dataclass
class FlatFaceGroup:
    group_index: int
    normal: np.ndarray          # unit outward normal
    area: float                 # total face area in mm²
    face_indices: List[int]     # trimesh face indices belonging to this group
    label: str = ""             # human-readable label

    def __post_init__(self):
        if not self.label:
            self.label = _make_label(self.normal, self.area, self.group_index)

    def to_dict(self) -> dict:
        return {
            "group_index": self.group_index,
            "normal": self.normal.tolist(),
            "area": round(self.area, 2),
            "label": self.label,
            "face_count": len(self.face_indices),
        }


def _make_label(normal: np.ndarray, area: float, idx: int) -> str:
    """Choose a human-readable direction name for a face group."""
    best_dot = -2.0
    best_name = f"Грань {idx + 1}"
    for ref_normal, name in _DIRECTION_LABELS:
        d = float(np.dot(normal, ref_normal))
        if d > best_dot:
            best_dot = d
            best_name = name
    return f"{best_name} ({area:.1f} мм²)"


def detect_flat_faces(
    mesh: trimesh.Trimesh,
    angle_tolerance_deg: float = 5.0,
    min_area_mm2: float = 1.0,
    max_groups: int = 12,
) -> List[FlatFaceGroup]:
    """
    Detect groups of coplanar (flat) faces in the mesh.

    Groups faces with nearly identical normals (within angle_tolerance_deg).
    Returns groups sorted by area descending, up to max_groups.

    Args:
        mesh: input trimesh
        angle_tolerance_deg: faces within this angle of each other are grouped
        min_area_mm2: groups with total area below this are discarded
        max_groups: return at most this many groups
    """
    face_normals = mesh.face_normals          # (F, 3)
    face_areas = mesh.area_faces               # (F,)

    n_faces = len(face_normals)
    assigned = np.full(n_faces, -1, dtype=int)
    cos_tol = np.cos(np.radians(angle_tolerance_deg))

    groups: List[FlatFaceGroup] = []
    group_id = 0

    for i in range(n_faces):
        if assigned[i] != -1:
            continue

        # Start new group with face i
        ref_normal = face_normals[i]
        dots = face_normals @ ref_normal  # (F,)
        members = np.where((assigned == -1) & (dots >= cos_tol))[0]

        if len(members) == 0:
            continue

        assigned[members] = group_id

        # Weighted average normal
        w = face_areas[members]
        avg_normal = (face_normals[members] * w[:, None]).sum(axis=0)
        norm_len = np.linalg.norm(avg_normal)
        if norm_len < 1e-10:
            continue
        avg_normal /= norm_len

        total_area = float(w.sum())
        if total_area < min_area_mm2:
            group_id += 1
            continue

        groups.append(FlatFaceGroup(
            group_index=group_id,
            normal=avg_normal,
            area=total_area,
            face_indices=members.tolist(),
        ))
        group_id += 1

    # Sort by area descending
    groups.sort(key=lambda g: g.area, reverse=True)

    # Re-index for clean display
    for i, g in enumerate(groups[:max_groups]):
        g.group_index = i

    result = groups[:max_groups]
    logger.info(f"detect_flat_faces: found {len(result)} flat face groups")
    return result


def compute_rotation_to_bed(face_normal: np.ndarray) -> np.ndarray:
    """
    Compute a 4x4 transformation matrix that rotates `face_normal` to point
    downward (-Z), i.e. placing that face on the bed.

    Returns a trimesh-compatible 4x4 homogeneous matrix.
    """
    face_normal = np.asarray(face_normal, dtype=float)
    face_normal = face_normal / (np.linalg.norm(face_normal) + 1e-12)

    target = np.array([0.0, 0.0, -1.0])   # bed direction

    dot = float(np.clip(np.dot(face_normal, target), -1.0, 1.0))

    if dot > 0.9999999:
        # Already pointing down
        return np.eye(4)

    if dot < -0.9999999:
        # Pointing straight up → rotate 180° around X
        rot3 = np.array([
            [1, 0, 0],
            [0, -1, 0],
            [0, 0, -1],
        ], dtype=float)
    else:
        axis = np.cross(face_normal, target)
        axis /= np.linalg.norm(axis)
        angle = np.arccos(dot)
        K = np.array([
            [0, -axis[2], axis[1]],
            [axis[2], 0, -axis[0]],
            [-axis[1], axis[0], 0],
        ])
        rot3 = np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * (K @ K)

    transform = np.eye(4)
    transform[:3, :3] = rot3
    return transform


def apply_face_to_bed(
    mesh: trimesh.Trimesh,
    face_normal: np.ndarray,
    output_path: Optional[str] = None,
) -> trimesh.Trimesh:
    """
    Rotate the mesh so that `face_normal` points down (onto the bed),
    then translate so that the lowest point sits at Z = 0.

    Args:
        mesh: input mesh
        face_normal: outward normal of the face to place on bed
        output_path: if provided, save the result as STL

    Returns:
        The rotated+translated mesh.
    """
    transform = compute_rotation_to_bed(face_normal)
    result = mesh.copy()
    result.apply_transform(transform)

    # Translate to bed (Z=0)
    min_z = result.bounds[0][2]
    result.apply_translation([0, 0, -min_z])

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        result.export(output_path)
        logger.info(f"apply_face_to_bed: saved to {output_path}")

    return result


def apply_face_to_bed_from_file(
    input_path: str,
    face_normal: np.ndarray,
    output_path: str,
) -> str:
    """
    Load mesh from file, rotate so face_normal is on bed, save to output_path.
    Returns output_path.
    """
    mesh = trimesh.load(input_path, force="mesh")
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(list(mesh.geometry.values()))

    apply_face_to_bed(mesh, face_normal, output_path=output_path)
    return output_path
