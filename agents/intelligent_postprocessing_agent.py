"""
Intelligent Post-Processing Agent for 3D print preparation
Analyzes geometry and makes autonomous decisions
Based on project_enhancements.md specifications
"""
import trimesh
import numpy as np
from typing import Dict, Literal, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
from api_clients.llm_client import LLMClient
from utils.logger import get_logger
from agents.orca_orientation_analyzer import OrcaOrientationAnalyzer
from agents.conical_overhang_fixer import ConicalOverhangFixer

logger = get_logger(__name__)


@dataclass
class ModelAnalysis:
    """Results of model geometry analysis"""
    complexity: Literal['simple', 'medium', 'complex']
    has_internal_cavities: bool
    max_overhang_angle: float
    overhang_area_mm2: float
    contact_area_mm2: float
    is_printable_without_supports: bool
    recommended_orientation: list  # np.ndarray converted to list
    recommended_support_strategy: Literal['none', 'minimal', 'standard', 'arc']
    print_difficulty: Literal['easy', 'medium', 'hard']
    reasoning: str = ""


class IntelligentPostProcessingAgent:
    """
    Intelligent agent for post-processing 3D models
    Analyzes geometry and makes autonomous decisions
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    async def process_intelligently(
        self,
        input_file: str,
        object_name: str,
        user_preferences: Dict,
        output_file: Optional[str] = None
    ) -> Dict:
        """
        Full cycle with analysis and decision making

        Args:
            input_file: Path to input 3D model (GLB/STL/OBJ)
            object_name: Name of the object
            user_preferences: User settings for processing
            output_file: Path for output file

        Returns:
            Dict with processed model info, analysis, decisions, reasoning
        """
        logger.info(f"Starting intelligent processing for: {object_name}")

        if output_file is None:
            input_path = Path(input_file)
            output_file = str(input_path.parent / f"{input_path.stem}_printable.stl")

        # 1. ANALYZE model geometry
        logger.info("Analyzing model geometry...")
        analysis = await self._analyze_model_geometry(input_file)

        # 2. MAKE DECISIONS based on analysis
        logger.info("Making processing decisions...")
        decisions = await self._make_processing_decisions(
            analysis,
            user_preferences
        )

        # 3. APPLY processing according to decisions
        logger.info("Applying processing...")
        processed_mesh, metadata = await self._apply_processing(
            input_file,
            decisions,
            analysis
        )

        # 4. GENERATE REASONING via LLM (optional)
        logger.info("Generating reasoning...")
        reasoning = await self._generate_reasoning(
            object_name,
            analysis,
            decisions
        )

        # 5. Export
        processed_mesh.export(output_file)
        logger.info(f"Processed model saved to: {output_file}")

        return {
            'object_name': object_name,
            'model_file': output_file,
            'analysis': asdict(analysis),
            'decisions': decisions,
            'reasoning': reasoning,
            'metadata': metadata,
            'preview_image': self._generate_preview_image(processed_mesh)
        }

    async def _analyze_model_geometry(self, input_file: str) -> ModelAnalysis:
        """Deep analysis of model geometry"""
        logger.debug(f"Loading mesh from: {input_file}")
        mesh = trimesh.load(input_file, force='mesh')

        # Basic metrics
        is_watertight = mesh.is_watertight
        n_faces = len(mesh.faces)

        # Complexity assessment
        if n_faces < 5000:
            complexity = 'simple'
        elif n_faces < 50000:
            complexity = 'medium'
        else:
            complexity = 'complex'

        logger.debug(f"Mesh complexity: {complexity} ({n_faces} faces)")

        # Detect internal cavities
        has_internal_cavities = self._detect_internal_cavities(mesh)

        # Analyze overhangs for ALL 6 orientations
        best_orientation, overhang_data = self._analyze_all_orientations(mesh)

        max_overhang_angle = overhang_data['max_overhang_angle']
        overhang_area = overhang_data['overhang_area']
        contact_area = overhang_data['contact_area']

        # Printability assessment
        is_printable_without_supports = (
            max_overhang_angle < 45.0 and
            contact_area > 100  # Minimum contact area
        )

        # Print difficulty
        if is_printable_without_supports:
            difficulty = 'easy'
        elif max_overhang_angle < 60 and not has_internal_cavities:
            difficulty = 'medium'
        else:
            difficulty = 'hard'

        # Recommended support strategy
        if is_printable_without_supports:
            support_strategy = 'none'
        elif has_internal_cavities:
            support_strategy = 'arc'  # Arc-overhang for internal cavities
        elif overhang_area < 500:  # mm²
            support_strategy = 'minimal'
        else:
            support_strategy = 'standard'

        return ModelAnalysis(
            complexity=complexity,
            has_internal_cavities=has_internal_cavities,
            max_overhang_angle=max_overhang_angle,
            overhang_area_mm2=overhang_area,
            contact_area_mm2=contact_area,
            is_printable_without_supports=is_printable_without_supports,
            recommended_orientation=best_orientation.tolist(),
            recommended_support_strategy=support_strategy,
            print_difficulty=difficulty
        )

    def _detect_internal_cavities(self, mesh) -> bool:
        """Detect internal cavities using split and volume analysis"""
        try:
            split_meshes = mesh.split()
            if len(split_meshes) > 1:
                logger.debug(f"Found {len(split_meshes)} disconnected components")
                return True
        except:
            pass

        return False

    def _analyze_all_orientations(
        self,
        mesh,
        critical_angle: float = 45.0,
        use_orca_orient: bool = True,
    ) -> tuple:
        """
        Find best print orientation.

        When use_orca_orient=True (default) uses the OrcaSlicer area-accumulation
        algorithm with its cost function (much better than 6 fixed rotations).
        Falls back to 6-rotation method on error.
        """
        if use_orca_orient:
            try:
                analyzer = OrcaOrientationAnalyzer(overhang_angle=critical_angle)
                rot3x3, orca_cost = analyzer.orient(mesh)

                # Build 4x4 transform
                transform = np.eye(4)
                transform[:3, :3] = rot3x3

                test_mesh = mesh.copy()
                test_mesh.apply_transform(transform)
                metrics = self._calculate_orientation_metrics(test_mesh, critical_angle)

                logger.info(
                    f"OrcaOrientationAnalyzer: unprintability={orca_cost.unprintability:.4f}, "
                    f"overhang_area={metrics['overhang_area']:.1f}mm²"
                )
                return transform, metrics
            except Exception as exc:
                logger.warning(f"OrcaOrientationAnalyzer failed, falling back to 6-rotation method: {exc}")

        # Fallback: test 6 axis-aligned orientations
        test_rotations = [
            np.eye(4),
            self._rotation_matrix_x(90),
            self._rotation_matrix_x(-90),
            self._rotation_matrix_y(90),
            self._rotation_matrix_y(-90),
            self._rotation_matrix_z(180)
        ]

        best_score = float('inf')
        best_transform = np.eye(4)
        best_data = {}

        for transform in test_rotations:
            test_mesh = mesh.copy()
            test_mesh.apply_transform(transform)

            metrics = self._calculate_orientation_metrics(test_mesh, critical_angle)

            score = (
                metrics['overhang_area'] * 1.0 +
                metrics['max_overhang_angle'] * 10.0 -
                metrics['contact_area'] * 0.5
            )

            if score < best_score:
                best_score = score
                best_transform = transform
                best_data = metrics

        return best_transform, best_data

    def _calculate_orientation_metrics(
        self,
        mesh,
        critical_angle: float
    ) -> Dict:
        """Calculate metrics for specific orientation"""
        up_vector = np.array([0, 0, 1])

        # Face angles relative to vertical
        face_angles_rad = np.arccos(
            np.clip(np.dot(mesh.face_normals, up_vector), -1, 1)
        )
        face_angles_deg = np.degrees(face_angles_rad)

        # Overhangs
        overhang_mask = face_angles_deg > critical_angle
        overhang_angles = face_angles_deg[overhang_mask]
        overhang_areas = mesh.area_faces[overhang_mask]

        max_overhang = float(np.max(overhang_angles)) if len(overhang_angles) > 0 else 0.0
        total_overhang_area = float(np.sum(overhang_areas))

        # Contact area (faces pointing down)
        contact_mask = (face_angles_deg > 170) & (face_angles_deg < 190)
        contact_area = float(np.sum(mesh.area_faces[contact_mask]))

        return {
            'max_overhang_angle': max_overhang,
            'overhang_area': total_overhang_area,
            'contact_area': contact_area,
            'n_overhang_faces': int(np.sum(overhang_mask))
        }

    async def _make_processing_decisions(
        self,
        analysis: ModelAnalysis,
        user_preferences: Dict
    ) -> Dict:
        """Make decisions based on analysis"""
        decisions = {
            'apply_mesh_repair': True,
            'apply_orientation': True,
            'orientation_strategy': 'optimal',
            'generate_supports': False,
            'support_type': 'none',
            'make_overhangs_printable': user_preferences.get('make_overhangs_printable', False),
            'overhang_max_angle': user_preferences.get('overhang_max_angle', 55.0),
            'overhang_max_hole_area': user_preferences.get('overhang_max_hole_area', 0.0),
            'overhang_layer_height': user_preferences.get('overhang_layer_height', 0.2),
            'overhang_method': user_preferences.get('overhang_method', 'voxel'),
            'warnings': []
        }

        # DECISION LOGIC

        # 1. Supports
        if analysis.is_printable_without_supports:
            decisions['generate_supports'] = False
            decisions['support_type'] = 'none'
        else:
            if user_preferences.get('generate_supports', True):
                decisions['generate_supports'] = True

                if analysis.recommended_support_strategy == 'arc':
                    decisions['support_type'] = 'arc'
                    decisions['warnings'].append(
                        "Internal cavities detected. Arc-overhang recommended."
                    )
                elif analysis.recommended_support_strategy == 'minimal':
                    decisions['support_type'] = 'minimal'
                else:
                    decisions['support_type'] = 'standard'
            else:
                decisions['warnings'].append(
                    f"Supports disabled but model has {analysis.max_overhang_angle:.1f}° overhangs!"
                )

        # 2. Orientation
        if user_preferences.get('auto_orient', True):
            decisions['orientation_strategy'] = 'optimal'
        else:
            decisions['orientation_strategy'] = 'user_defined'

        # 3. Print difficulty warnings
        if analysis.print_difficulty == 'hard':
            decisions['warnings'].append(
                "This model is difficult to print. Consider redesigning."
            )

        # 4. Internal cavities
        if analysis.has_internal_cavities and decisions['support_type'] != 'arc':
            decisions['warnings'].append(
                "Internal cavities detected. Supports may be hard to remove."
            )

        return decisions

    async def _apply_processing(
        self,
        input_file: str,
        decisions: Dict,
        analysis: ModelAnalysis
    ) -> tuple:
        """Apply processing according to decisions"""
        mesh = trimesh.load(input_file, force='mesh')
        processing_log = []

        # 1. Mesh Repair
        if decisions['apply_mesh_repair']:
            if not mesh.is_watertight:
                trimesh.repair.fix_normals(mesh)
                trimesh.repair.fill_holes(mesh)
                trimesh.repair.fix_winding(mesh)
                processing_log.append("✓ Mesh repaired (holes filled, normals fixed)")
            else:
                processing_log.append("✓ Mesh is watertight (no repair needed)")

        # 2. Orientation
        if decisions['apply_orientation'] and decisions['orientation_strategy'] == 'optimal':
            orientation_matrix = np.array(analysis.recommended_orientation)
            mesh.apply_transform(orientation_matrix)
            processing_log.append(
                f"✓ Orientation optimized (max overhang: {analysis.max_overhang_angle:.1f}°)"
            )

        # 3. Make overhangs printable (conical geometry modification)
        if decisions.get('make_overhangs_printable', False):
            try:
                overhang_method = decisions.get('overhang_method', 'voxel')
                fixer = ConicalOverhangFixer(
                    layer_height=decisions.get('overhang_layer_height', 0.2),
                    max_angle=decisions.get('overhang_max_angle', 55.0),
                    max_hole_area=decisions.get('overhang_max_hole_area', 0.0),
                )
                logger.info(f"Applying conical overhang fix (method={overhang_method})...")
                fixed_mesh = fixer.fix(mesh, method=overhang_method)
                if len(fixed_mesh.vertices) > 0:
                    mesh = fixed_mesh
                    processing_log.append(
                        f"✓ Overhangs made printable (conical fix, max angle: "
                        f"{decisions.get('overhang_max_angle', 55.0):.0f}°)"
                    )
                else:
                    processing_log.append("⚠ Conical overhang fix produced empty mesh, skipped")
            except Exception as exc:
                logger.warning(f"Conical overhang fix failed: {exc}")
                processing_log.append(f"⚠ Conical overhang fix failed: {exc}")

        # 4. Position on build plate
        mesh.apply_translation(-mesh.center_mass)
        mesh.apply_translation([0, 0, -mesh.bounds[0][2]])
        processing_log.append("✓ Positioned on build plate")

        # 5. Supports (noted but not physically generated in this version)
        if decisions['generate_supports']:
            processing_log.append(
                f"✓ {decisions['support_type'].capitalize()} supports recommended"
            )

        metadata = {
            'volume_mm3': float(mesh.volume),
            'surface_area_mm2': float(mesh.area),
            'bounding_box_mm': mesh.bounds.tolist(),
            'processing_log': processing_log,
            'warnings': decisions['warnings'],
            'estimated_print_time_h': self._estimate_print_time(mesh),
            'estimated_material_g': self._estimate_material(mesh)
        }

        return mesh, metadata

    async def _generate_reasoning(
        self,
        object_name: str,
        analysis: ModelAnalysis,
        decisions: Dict
    ) -> str:
        """Generate human-readable reasoning"""
        if self.llm is None:
            return self._simple_reasoning(object_name, analysis, decisions)

        prompt = f"""
You are a 3D printing expert. Explain your decisions about post-processing this model.

Object: {object_name}

Analysis:
- Complexity: {analysis.complexity}
- Max overhang angle: {analysis.max_overhang_angle:.1f}°
- Overhang area: {analysis.overhang_area_mm2:.1f} mm²
- Contact area: {analysis.contact_area_mm2:.1f} mm²
- Internal cavities: {"Yes" if analysis.has_internal_cavities else "No"}
- Print difficulty: {analysis.print_difficulty}

Decisions made:
- Supports: {decisions['support_type']}
- Orientation: {decisions['orientation_strategy']}

Explain in 2-3 sentences why these decisions were made and what the user should expect.
"""

        try:
            response = await self.llm.complete(prompt, temperature=0.7)
            return response
        except:
            return self._simple_reasoning(object_name, analysis, decisions)

    def _simple_reasoning(
        self,
        object_name: str,
        analysis: ModelAnalysis,
        decisions: Dict
    ) -> str:
        """Simple reasoning without LLM"""
        reasoning = f"**{object_name}** analysis:\n\n"

        if analysis.is_printable_without_supports:
            reasoning += "✅ This model can be printed **without supports** in the recommended orientation.\n"
        else:
            reasoning += f"⚠️ Model has {analysis.max_overhang_angle:.1f}° overhangs. "

            if decisions['support_type'] == 'arc':
                reasoning += "Using **arc-overhang** strategy for internal cavities.\n"
            elif decisions['support_type'] == 'none':
                reasoning += "**No supports** will be generated (user preference). Print may fail!\n"
            else:
                reasoning += f"**{decisions['support_type'].capitalize()} supports** recommended.\n"

        reasoning += f"\n**Print difficulty:** {analysis.print_difficulty.upper()}\n"

        if decisions['warnings']:
            reasoning += "\n**Warnings:**\n"
            for warning in decisions['warnings']:
                reasoning += f"- {warning}\n"

        return reasoning

    def _estimate_print_time(self, mesh) -> float:
        """Estimate print time in hours"""
        volume_cm3 = mesh.volume / 1000
        return (volume_cm3 * 17.5) / 60

    def _estimate_material(self, mesh) -> float:
        """Estimate material usage in grams"""
        volume_cm3 = mesh.volume / 1000
        return volume_cm3 * 1.25  # PLA density

    def _generate_preview_image(self, mesh) -> str:
        """Generate preview image of processed mesh"""
        try:
            import matplotlib.pyplot as plt
            from mpl_toolkits.mplot3d import Axes3D

            fig = plt.figure(figsize=(8, 8))
            ax = fig.add_subplot(111, projection='3d')

            # Sample vertices for performance
            sample_rate = max(1, len(mesh.vertices) // 10000)
            sampled_vertices = mesh.vertices[::sample_rate]
            sampled_faces = mesh.faces[::sample_rate]

            ax.plot_trisurf(
                sampled_vertices[:, 0],
                sampled_vertices[:, 1],
                sampled_vertices[:, 2],
                triangles=sampled_faces,
                cmap='viridis',
                alpha=0.8,
                edgecolor='none'
            )

            ax.set_xlabel('X (mm)')
            ax.set_ylabel('Y (mm)')
            ax.set_zlabel('Z (mm)')
            ax.set_title('Processed Model')

            preview_path = f"outputs/previews/model_preview_{hash(str(mesh.vertices[:100]))}.png"
            Path(preview_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(preview_path, dpi=150, bbox_inches='tight')
            plt.close()

            return preview_path
        except Exception as e:
            logger.warning(f"Failed to generate preview image: {e}")
            return ""

    # Helper rotation matrices
    def _rotation_matrix_x(self, degrees: float) -> np.ndarray:
        """Rotation matrix around X axis"""
        rad = np.radians(degrees)
        return np.array([
            [1, 0, 0, 0],
            [0, np.cos(rad), -np.sin(rad), 0],
            [0, np.sin(rad), np.cos(rad), 0],
            [0, 0, 0, 1]
        ])

    def _rotation_matrix_y(self, degrees: float) -> np.ndarray:
        """Rotation matrix around Y axis"""
        rad = np.radians(degrees)
        return np.array([
            [np.cos(rad), 0, np.sin(rad), 0],
            [0, 1, 0, 0],
            [-np.sin(rad), 0, np.cos(rad), 0],
            [0, 0, 0, 1]
        ])

    def _rotation_matrix_z(self, degrees: float) -> np.ndarray:
        """Rotation matrix around Z axis"""
        rad = np.radians(degrees)
        return np.array([
            [np.cos(rad), -np.sin(rad), 0, 0],
            [np.sin(rad), np.cos(rad), 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])

    def __repr__(self):
        return f"IntelligentPostProcessingAgent(llm={'enabled' if self.llm else 'disabled'})"
