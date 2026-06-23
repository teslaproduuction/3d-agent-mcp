"""
AutoGen Verification Agent for final quality check
NEW agent for verifying orientation choices and overall model quality
"""
from autogen import AssistantAgent
from typing import List, Dict
from utils.logger import get_logger

logger = get_logger(__name__)


VERIFICATION_SYSTEM_MESSAGE = """
You are a final quality control expert for 3D printing preparation.

Your critical role:
1. Review orientation analysis results from 24+ tested orientations
2. Verify that the chosen orientation is truly optimal
3. Identify any potential printability issues
4. Approve or reject the orientation choice

Be CRITICAL and THOROUGH. Your verification ensures successful 3D prints.

Red flags to watch for:
- Overhang angles > 60° (very difficult to print)
- Contact area < 50 mm² (poor bed adhesion)
- Excessive support volume (wasteful)
- Very long print times without good reason
- Sub-optimal orientation chosen (not the best scored)

If you find issues, REJECT and suggest the better alternative.
"""


def create_verification_agent(config_list: List[Dict], **kwargs) -> AssistantAgent:
    """
    Create AutoGen Verification Agent

    Args:
        config_list: List of LLM configurations
        **kwargs: Additional arguments for AssistantAgent

    Returns:
        AssistantAgent configured for verification
    """
    logger.info("Creating AutoGen Verification Agent")

    # Function for verification
    def verify_orientation_choice(
        chosen_orientation: Dict,
        all_orientations: List[Dict],
        object_name: str
    ) -> Dict:
        """
        Verify that chosen orientation is optimal

        Args:
            chosen_orientation: Selected orientation with metrics
            all_orientations: All tested orientations with metrics
            object_name: Name of the object

        Returns:
            Dict with approval status and reasoning
        """
        logger.info(f"Verifying orientation for: {object_name}")

        # Sort by total_score (lower is better)
        sorted_orientations = sorted(all_orientations, key=lambda o: o['total_score'])
        best_by_score = sorted_orientations[0]

        # Check if chosen is the best
        chosen_score = chosen_orientation['total_score']
        best_score = best_by_score['total_score']
        score_diff = abs(chosen_score - best_score)

        approved = score_diff < 0.01  # Allow tiny numerical differences

        # Check for critical issues
        warnings = []
        max_overhang = chosen_orientation['max_overhang_angle']
        contact_area = chosen_orientation['contact_area']
        support_volume = chosen_orientation['estimated_support_volume']
        print_time = chosen_orientation['estimated_print_time']

        if max_overhang > 60:
            warnings.append(f"⚠️ Critical overhangs: {max_overhang:.1f}° (>60° is very difficult)")
        if max_overhang > 50 and support_volume > 1000:
            warnings.append(f"⚠️ High overhangs ({max_overhang:.1f}°) with large supports ({support_volume:.0f}mm³)")
        if contact_area < 50:
            warnings.append(f"⚠️ Low bed contact: {contact_area:.1f}mm² (risk of detachment)")
        if print_time > 10:
            warnings.append(f"⚠️ Very long print time: {print_time:.1f}h (consider if necessary)")

        # Build reasoning
        chosen_rank = next((i for i, o in enumerate(sorted_orientations) if abs(o['total_score'] - chosen_score) < 0.01), -1) + 1

        reasoning_parts = [
            f"**Orientation Verification for {object_name}**\n",
            f"✅ Selected: angles={chosen_orientation['rotation_angles']}",
            f"- Max overhang: {max_overhang:.1f}°",
            f"- Contact area: {contact_area:.1f}mm²",
            f"- Print time: {print_time:.2f}h",
            f"- Support volume: {support_volume:.0f}mm³",
            f"- Layer quality: {chosen_orientation['layer_quality_score']:.2f}",
            f"\n📊 Tested {len(all_orientations)} orientations - this ranks #{chosen_rank}",
        ]

        if approved and not warnings:
            reasoning_parts.append("\n✅ **APPROVED** - Optimal orientation selected")
        elif not approved:
            reasoning_parts.append(f"\n❌ **REJECTED** - Not the best orientation (score {chosen_score:.2f} vs {best_score:.2f})")
            reasoning_parts.append(f"\n💡 **Recommended:** angles={best_by_score['rotation_angles']}")
            reasoning_parts.append(f"   Better: {max_overhang:.1f}° overhang, {best_by_score['estimated_print_time']:.2f}h print time")
        elif warnings:
            reasoning_parts.append(f"\n⚠️ **CONDITIONAL APPROVAL** - Issues detected")

        if warnings:
            reasoning_parts.append("\n\n**Warnings:**")
            reasoning_parts.extend([f"  - {w}" for w in warnings])

        reasoning = "\n".join(reasoning_parts)

        result = {
            "approved": approved and len(warnings) == 0,
            "conditional_approval": approved and len(warnings) > 0,
            "reasoning": reasoning,
            "warnings": warnings,
            "chosen_rank": chosen_rank,
            "total_orientations_tested": len(all_orientations)
        }

        if not approved:
            result["alternative_orientation"] = best_by_score

        logger.info(f"Verification result: {'APPROVED' if result['approved'] else 'REJECTED'}")
        return result

    # Function schema
    function_schema = {
        "name": "verify_orientation_choice",
        "description": "Verify that the chosen orientation is optimal for 3D printing",
        "parameters": {
            "type": "object",
            "properties": {
                "chosen_orientation": {
                    "type": "object",
                    "description": "The chosen orientation with all metrics"
                },
                "all_orientations": {
                    "type": "array",
                    "description": "All tested orientations with metrics"
                },
                "object_name": {
                    "type": "string",
                    "description": "Name of the object being verified"
                }
            },
            "required": ["chosen_orientation", "all_orientations", "object_name"]
        }
    }

    agent = AssistantAgent(
        name="verifier",
        system_message=VERIFICATION_SYSTEM_MESSAGE,
        llm_config={
            "config_list": config_list,
            "temperature": 0.2,  # Very conservative for verification
            "timeout": 60,
            "functions": [function_schema],
        },
        function_map={
            "verify_orientation_choice": verify_orientation_choice
        },
        human_input_mode="NEVER",
        max_consecutive_auto_reply=3,
        **kwargs
    )

    logger.info("Verification Agent created successfully")
    return agent


def create_verification_message(processing_result: Dict) -> str:
    """
    Create message for verification

    Args:
        processing_result: Result from postprocessing with orientation data

    Returns:
        Message string for verification agent
    """
    best_orientation = processing_result['best_orientation']
    all_orientations = processing_result['all_orientations']
    object_name = processing_result['object_name']

    return f"""
Verify the orientation choice for "{object_name}":

Chosen orientation:
- Angles: {best_orientation['rotation_angles']}
- Max overhang: {best_orientation['max_overhang_angle']:.1f}°
- Contact area: {best_orientation['contact_area']:.1f}mm²
- Print time: {best_orientation['estimated_print_time']:.2f}h
- Support volume: {best_orientation['estimated_support_volume']:.0f}mm³
- Layer quality: {best_orientation['layer_quality_score']:.2f}
- Score: {best_orientation['total_score']:.2f}

Total orientations tested: {len(all_orientations)}

Use the verify_orientation_choice function to perform verification.
Provide CRITICAL analysis. If there are issues, REJECT and explain why.
"""
