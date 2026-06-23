"""
Enhanced Orientation Analyzer with 24+ orientation testing
Extends the existing 6-orientation analysis with more comprehensive testing
"""
import trimesh
import numpy as np
from typing import Tuple, List, Dict
from dataclasses import dataclass, asdict
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OrientationMetrics:
    """Comprehensive orientation metrics"""
    transform: np.ndarray
    rotation_angles: Tuple[float, float, float]

    # Geometric metrics (existing)
    max_overhang_angle: float
    overhang_area: float
    contact_area: float

    # NEW metrics
    estimated_print_time: float       # hours
    estimated_support_volume: float   # mm³
    layer_quality_score: float        # 0-1 (higher is better)
    total_score: float                # lower is better


class EnhancedOrientationAnalyzer:
    """
    Enhanced analyzer for 3D model orientation
    Supports 6, 24, or 48 orientation tests with comprehensive metrics
    """

    def __init__(
        self,
        num_orientations: int = 24,
        critical_angle: float = 45.0,
        layer_height: float = 0.2,
        print_speed: float = 50.0,
        scoring_weights: Dict[str, float] = None
    ):
        """
        Args:
            num_orientations: Number of orientations to test (6, 24, or 48)
            critical_angle: Critical overhang angle in degrees
            layer_height: Layer height in mm
            print_speed: Print speed in mm/s
            scoring_weights: Dict with weights for scoring metrics
        """
        self.num_orientations = num_orientations
        self.critical_angle = critical_angle
        self.layer_height = layer_height
        self.print_speed = print_speed

        # Default scoring weights
        self.weights = scoring_weights or {
            'overhang_angle': 10.0,
            'overhang_area': 1.0,
            'support_volume': 0.1,
            'print_time': 50.0,
            'contact_area': -0.5,      # Negative = larger is better
            'layer_quality': -100.0,   # Negative = higher is better
        }

        logger.info(f"EnhancedOrientationAnalyzer initialized: {num_orientations} orientations")

    def analyze_all_orientations(
        self,
        mesh: trimesh.Trimesh
    ) -> Tuple[np.ndarray, List[OrientationMetrics]]:
        """
        Test multiple orientations and return best

        Args:
            mesh: Input mesh

        Returns:
            Tuple of (best_transform, all_metrics)
        """
        test_rotations = self._generate_test_rotations(self.num_orientations)

        all_metrics = []
        for transform, angles in test_rotations:
            test_mesh = mesh.copy()
            test_mesh.apply_transform(transform)

            metrics = self._calculate_comprehensive_metrics(
                test_mesh, transform, angles
            )
            all_metrics.append(metrics)

        # Sort by total_score (lower is better)
        all_metrics.sort(key=lambda m: m.total_score)

        best_transform = all_metrics[0].transform
        logger.info(f"Best orientation: angles={all_metrics[0].rotation_angles}, score={all_metrics[0].total_score:.2f}")

        return best_transform, all_metrics

    def _generate_test_rotations(
        self,
        num_orientations: int
    ) -> List[Tuple[np.ndarray, Tuple[float, float, float]]]:
        """
        Generate test rotations

        Args:
            num_orientations: 6, 24, or 48

        Returns:
            List of (transform_matrix, rotation_angles)
        """
        if num_orientations == 6:
            return self._generate_6_orientations()
        elif num_orientations == 24:
            return self._generate_24_orientations()
        elif num_orientations == 48:
            return self._generate_48_orientations()
        else:
            logger.warning(f"Unsupported num_orientations={num_orientations}, using 24")
            return self._generate_24_orientations()

    def _generate_6_orientations(self) -> List[Tuple[np.ndarray, Tuple[float, float, float]]]:
        """Generate 6 basic orientations (cube faces)"""
        rotations = [
            (0, 0, 0),      # Base
            (90, 0, 0),     # +90° X
            (-90, 0, 0),    # -90° X
            (0, 90, 0),     # +90° Y
            (0, -90, 0),    # -90° Y
            (0, 0, 180)     # 180° Z
        ]

        return [(self._rotation_matrix(*angles), angles) for angles in rotations]

    def _generate_24_orientations(self) -> List[Tuple[np.ndarray, Tuple[float, float, float]]]:
        """
        Generate 24 orientations:
        - 6 faces
        - 12 edges
        - 6 corners
        """
        # 6 faces
        face_rotations = [
            (0, 0, 0), (180, 0, 0), (90, 0, 0), (-90, 0, 0), (0, 90, 0), (0, -90, 0)
        ]

        # 12 edges
        edge_rotations = [
            (45, 0, 0), (-45, 0, 0), (0, 45, 0), (0, -45, 0),
            (45, 45, 0), (45, -45, 0), (-45, 45, 0), (-45, -45, 0),
            (90, 45, 0), (90, -45, 0), (-90, 45, 0), (-90, -45, 0),
        ]

        # 6 corners
        corner_rotations = [
            (45, 45, 45), (-45, -45, -45),
            (45, -45, 45), (-45, 45, -45),
            (45, 45, -45), (-45, -45, 45),
        ]

        all_rotations = face_rotations + edge_rotations + corner_rotations
        return [(self._rotation_matrix(*angles), angles) for angles in all_rotations]

    def _generate_48_orientations(self) -> List[Tuple[np.ndarray, Tuple[float, float, float]]]:
        """Generate 48 orientations with finer angular resolution"""
        # Start with 24 orientations
        orientations = self._generate_24_orientations()

        # Add intermediate angles
        additional_rotations = [
            (30, 0, 0), (-30, 0, 0), (60, 0, 0), (-60, 0, 0),
            (0, 30, 0), (0, -30, 0), (0, 60, 0), (0, -60, 0),
            (30, 30, 0), (30, -30, 0), (-30, 30, 0), (-30, -30, 0),
            (60, 30, 0), (60, -30, 0), (-60, 30, 0), (-60, -30, 0),
            (30, 30, 30), (-30, -30, -30),
            (30, -30, 30), (-30, 30, -30),
            (30, 30, -30), (-30, -30, 30),
            (60, 45, 30), (-60, -45, -30),
        ]

        orientations.extend([
            (self._rotation_matrix(*angles), angles) for angles in additional_rotations
        ])

        return orientations

    def _rotation_matrix(self, x_deg: float, y_deg: float, z_deg: float) -> np.ndarray:
        """Create 4x4 rotation matrix from Euler angles"""
        x_rad = np.radians(x_deg)
        y_rad = np.radians(y_deg)
        z_rad = np.radians(z_deg)

        # Rotation matrices
        rx = np.array([
            [1, 0, 0],
            [0, np.cos(x_rad), -np.sin(x_rad)],
            [0, np.sin(x_rad), np.cos(x_rad)]
        ])

        ry = np.array([
            [np.cos(y_rad), 0, np.sin(y_rad)],
            [0, 1, 0],
            [-np.sin(y_rad), 0, np.cos(y_rad)]
        ])

        rz = np.array([
            [np.cos(z_rad), -np.sin(z_rad), 0],
            [np.sin(z_rad), np.cos(z_rad), 0],
            [0, 0, 1]
        ])

        # Combined rotation
        rotation = rz @ ry @ rx

        # 4x4 transformation matrix
        transform = np.eye(4)
        transform[:3, :3] = rotation

        return transform

    def _calculate_comprehensive_metrics(
        self,
        mesh: trimesh.Trimesh,
        transform: np.ndarray,
        angles: Tuple[float, float, float]
    ) -> OrientationMetrics:
        """
        Calculate all metrics for a specific orientation

        Args:
            mesh: Test mesh (already transformed)
            transform: Transformation matrix
            angles: Rotation angles

        Returns:
            OrientationMetrics
        """
        up_vector = np.array([0, 0, 1])

        # Face angles relative to build plate
        face_angles_deg = np.degrees(
            np.arccos(np.clip(np.dot(mesh.face_normals, up_vector), -1, 1))
        )

        # Overhang metrics
        overhang_mask = face_angles_deg > self.critical_angle
        max_overhang_angle = float(np.max(face_angles_deg[overhang_mask])) if np.any(overhang_mask) else 0.0
        total_overhang_area = float(np.sum(mesh.area_faces[overhang_mask]))

        # Contact area (faces parallel to build plate)
        contact_mask = (face_angles_deg > 170) & (face_angles_deg < 190)
        contact_area = float(np.sum(mesh.area_faces[contact_mask]))

        # NEW: Print time estimation
        z_height = mesh.bounds[1][2] - mesh.bounds[0][2]
        n_layers = int(np.ceil(z_height / self.layer_height))

        # Estimate perimeter length per layer
        perimeter_per_layer = self._estimate_perimeter_length(mesh)
        time_per_layer = perimeter_per_layer / self.print_speed / 3600  # hours
        estimated_print_time = n_layers * time_per_layer

        # NEW: Support volume estimation
        # Rough estimation: overhang area * layer_height * support density factor
        estimated_support_volume = total_overhang_area * self.layer_height * 10

        # NEW: Layer quality score
        # Quality is best when faces are at 90° to build plate
        quality_scores = 1.0 - np.abs(face_angles_deg - 90) / 90.0
        layer_quality_score = float(np.mean(quality_scores))

        # Weighted total score (lower is better)
        total_score = (
            max_overhang_angle * self.weights['overhang_angle'] +
            total_overhang_area * self.weights['overhang_area'] +
            estimated_support_volume * self.weights['support_volume'] +
            estimated_print_time * self.weights['print_time'] +
            contact_area * self.weights['contact_area'] +
            layer_quality_score * self.weights['layer_quality']
        )

        return OrientationMetrics(
            transform=transform,
            rotation_angles=angles,
            max_overhang_angle=max_overhang_angle,
            overhang_area=total_overhang_area,
            contact_area=contact_area,
            estimated_print_time=estimated_print_time,
            estimated_support_volume=estimated_support_volume,
            layer_quality_score=layer_quality_score,
            total_score=total_score
        )

    def _estimate_perimeter_length(self, mesh: trimesh.Trimesh) -> float:
        """
        Estimate average perimeter length per layer

        Args:
            mesh: Input mesh

        Returns:
            Estimated perimeter length in mm
        """
        # Rough estimation based on bounding box
        bounds = mesh.bounds
        xy_dimensions = bounds[1][:2] - bounds[0][:2]
        perimeter = 2 * (xy_dimensions[0] + xy_dimensions[1])

        return perimeter


def metrics_to_dict(metrics: OrientationMetrics) -> Dict:
    """Convert OrientationMetrics to dictionary (for JSON serialization)"""
    metrics_dict = asdict(metrics)
    # Convert numpy array to list
    metrics_dict['transform'] = metrics.transform.tolist()
    return metrics_dict
