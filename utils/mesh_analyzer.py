"""
Mesh analyzer — computes GCI and quality metrics for generated 3D models.

GCI formula (Фролов, 2025):
    GCI = w1*(Nf/A) + w2*(C/L) + w3*(Vc/Vt)

where:
    Nf  — number of faces
    A   — surface area (cm²)
    C   — total edge length (cm)
    L   — characteristic size / max extent (cm)
    Vc  — volume of internal cavities (cm³); 0 if solid
    Vt  — total volume (cm³)

Weights (from article):
    w1 = 0.0002  (mesh density)
    w2 = 0.0028  (topological complexity)
    w3 = 0.9970  (internal cavities — dominant factor)

GCI thresholds:
    < 0.5  → simple geometry, MAE < 0.3 mm (direct use OK)
    0.5–0.8 → medium complexity, MAE ≈ 0.8–1.2 mm
    ≥ 0.8  → complex, MAE > 1.5 mm (CAD post-editing recommended)
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# GCI weights from the article
_W1 = 0.0002
_W2 = 0.0028
_W3 = 0.9970

# Predicted MAE from regression: MAE = 2.08 * GCI - 0.48  (clamped to ≥ 0)
# Predicted RMSE: RMSE = 3.58 * GCI - 0.86
_MAE_A, _MAE_B   = 2.08, -0.48
_RMSE_A, _RMSE_B = 3.58, -0.86


@dataclass
class MeshMetrics:
    # Raw geometry
    face_count:             int   = 0
    vertex_count:           int   = 0
    surface_area_cm2:       float = 0.0
    total_volume_cm3:       float = 0.0
    char_size_cm:           float = 0.0    # max bounding-box extent
    edge_length_total_cm:   float = 0.0
    cavity_volume_cm3:      float = 0.0   # 0 for solid meshes

    # GCI
    gci_surface:            float = 0.0   # w1 * (Nf / A)
    gci_topology:           float = 0.0   # w2 * (C / L)
    gci_cavity:             float = 0.0   # w3 * (Vc / Vt)
    gci_total:              float = 0.0

    # Quality flags
    is_manifold:            bool  = False
    non_manifold_edges:     int   = 0
    component_count:        int   = 1
    file_size_mb:           float = 0.0

    # Predicted accuracy (from regression equations in the article)
    predicted_mae_mm:       float = 0.0
    predicted_rmse_mm:      float = 0.0
    gci_category:           str   = ""    # simple / medium / complex

    error:                  str   = ""


def analyze_mesh(path: str | Path, units: str = "mm") -> MeshMetrics:
    """
    Analyze a 3D model file and compute GCI + quality metrics.

    Args:
        path:  Path to .glb / .obj / .stl file.
        units: Units of the mesh ('mm' or 'cm').  GLB files from Hunyuan3D are in mm.

    Returns:
        MeshMetrics dataclass.
    """
    m = MeshMetrics()
    path = Path(path)

    if not path.exists():
        m.error = f"File not found: {path}"
        return m

    m.file_size_mb = path.stat().st_size / 1024**2

    try:
        import trimesh
        scene = trimesh.load(str(path), force="scene", process=False)

        # Flatten scene → single mesh for analysis
        if isinstance(scene, trimesh.Scene):
            geoms = list(scene.geometry.values())
            if not geoms:
                m.error = "Empty scene"
                return m
            mesh = trimesh.util.concatenate(geoms) if len(geoms) > 1 else geoms[0]
            m.component_count = len(geoms)
        elif isinstance(scene, trimesh.Trimesh):
            mesh = scene
            m.component_count = 1
        else:
            m.error = f"Unsupported mesh type: {type(scene)}"
            return m

        if not isinstance(mesh, trimesh.Trimesh):
            m.error = "Could not produce Trimesh"
            return m

        # ── Unit conversion ─────────────────────────────────────────────
        # Hunyuan3D outputs in mm; article uses cm for all formulas
        scale = 0.1 if units == "mm" else 1.0  # mm→cm

        # ── Face / vertex counts ────────────────────────────────────────
        m.face_count   = len(mesh.faces)
        m.vertex_count = len(mesh.vertices)

        # ── Surface area ────────────────────────────────────────────────
        m.surface_area_cm2 = float(mesh.area) * (scale ** 2)

        # ── Total edge length ───────────────────────────────────────────
        # unique_edges returns pairs of vertex indices; compute lengths
        edges = mesh.vertices[mesh.edges_unique]            # (E, 2, 3)
        edge_vecs = edges[:, 1] - edges[:, 0]               # (E, 3)
        edge_lengths = float(((edge_vecs ** 2).sum(axis=1) ** 0.5).sum())
        m.edge_length_total_cm = edge_lengths * scale

        # ── Characteristic size (max bounding-box extent) ───────────────
        extents = mesh.bounding_box.extents                 # [dx, dy, dz]
        m.char_size_cm = float(max(extents)) * scale

        # ── Volume ──────────────────────────────────────────────────────
        m.is_manifold = mesh.is_watertight
        if mesh.is_watertight:
            m.total_volume_cm3 = abs(float(mesh.volume)) * (scale ** 3)
            # Cavity volume: convex hull volume minus actual volume
            hull_vol = abs(float(mesh.convex_hull.volume)) * (scale ** 3)
            m.cavity_volume_cm3 = max(0.0, hull_vol - m.total_volume_cm3)
        else:
            # Fallback: use bounding box fraction
            bbox_vol = float(mesh.bounding_box.volume) * (scale ** 3)
            m.total_volume_cm3 = bbox_vol * 0.5   # rough estimate
            m.cavity_volume_cm3 = 0.0

        # ── Non-manifold edges ──────────────────────────────────────────
        try:
            m.non_manifold_edges = int(len(mesh.as_open_bounds().edges)
                                        if hasattr(mesh, "as_open_bounds") else 0)
        except Exception:
            m.non_manifold_edges = 0 if mesh.is_watertight else -1

        # ── GCI computation ─────────────────────────────────────────────
        A  = m.surface_area_cm2
        Nf = m.face_count
        C  = m.edge_length_total_cm
        L  = m.char_size_cm
        Vc = m.cavity_volume_cm3
        Vt = m.total_volume_cm3

        m.gci_surface  = _W1 * (Nf / A)           if A  > 0 else 0.0
        m.gci_topology = _W2 * (C / L)             if L  > 0 else 0.0
        m.gci_cavity   = _W3 * (Vc / Vt)           if Vt > 0 else 0.0
        m.gci_total    = m.gci_surface + m.gci_topology + m.gci_cavity

        # ── Regression predictions (from article) ───────────────────────
        m.predicted_mae_mm  = max(0.0, _MAE_A  * m.gci_total + _MAE_B)
        m.predicted_rmse_mm = max(0.0, _RMSE_A * m.gci_total + _RMSE_B)

        if m.gci_total < 0.5:
            m.gci_category = "🟢 Простая (GCI < 0.5)"
        elif m.gci_total < 0.8:
            m.gci_category = "🟡 Средняя (GCI 0.5–0.8)"
        else:
            m.gci_category = "🔴 Сложная (GCI ≥ 0.8)"

    except ImportError:
        m.error = "trimesh not installed"
    except Exception as e:
        logger.warning(f"Mesh analysis failed for {path}: {e}", exc_info=True)
        m.error = str(e)

    return m


def gci_category_label(gci: float) -> str:
    if gci < 0.5:
        return "🟢 Простая"
    elif gci < 0.8:
        return "🟡 Средняя"
    return "🔴 Сложная"


def predicted_mae(gci: float) -> float:
    return max(0.0, _MAE_A * gci + _MAE_B)


def predicted_rmse(gci: float) -> float:
    return max(0.0, _RMSE_A * gci + _RMSE_B)
