"""
AutoGen Planner Agent for decomposing user requests into 3D generation tasks
"""
from autogen import AssistantAgent
from typing import List, Dict
from utils.logger import get_logger

logger = get_logger(__name__)


PLANNER_SYSTEM_MESSAGE = """
You are a 3D generation planning expert. Your task is to analyze user requests and break them down into individual 3D objects that need to be generated.

For each object, you need to:
1. Identify the object name
2. Create a detailed 3D generation prompt
3. Assign priority (1 = highest)
4. Specify quantity if multiple copies needed

Guidelines:
- Be specific and descriptive in prompts
- Include materials, style, and important details
- Consider how objects will be 3D printed
- Break complex assemblies into individual parts
- Always think about printability: avoid overhangs, ensure structural integrity

Example:
User: "A desk organizer with pen holder and phone stand"

Output:
[
  {
    "object": "desk organizer base",
    "prompt": "rectangular desk organizer base with compartments, minimalist design, white matte finish, suitable for 3D printing",
    "priority": 1,
    "quantity": 1
  },
  {
    "object": "pen holder",
    "prompt": "cylindrical pen holder with 5 slots, modern design, integrated mounting for desk organizer",
    "priority": 2,
    "quantity": 1
  },
  {
    "object": "phone stand",
    "prompt": "angled phone stand with anti-slip surface, adjustable angle, mounts to desk organizer",
    "priority": 3,
    "quantity": 1
  }
]

Always output valid JSON array. Be concise and practical.
"""


def create_planner_agent(config_list: List[Dict], **kwargs) -> AssistantAgent:
    """
    Create AutoGen Planner Agent

    Args:
        config_list: List of LLM configurations for AutoGen
        **kwargs: Additional arguments for AssistantAgent

    Returns:
        AssistantAgent configured as planner
    """
    logger.info("Creating AutoGen Planner Agent")

    agent = AssistantAgent(
        name="planner",
        system_message=PLANNER_SYSTEM_MESSAGE,
        llm_config={
            "config_list": config_list,
            "temperature": 0.7,
            "timeout": 120,
        },
        max_consecutive_auto_reply=5,
        human_input_mode="NEVER",
        **kwargs
    )

    logger.info("Planner Agent created successfully")
    return agent


def refine_prompts_message(scene_plan: List[Dict]) -> str:
    """
    Create message for refining prompts

    Args:
        scene_plan: List of objects from planning

    Returns:
        Message string for LLM
    """
    objects_list = "\n".join([
        f"- {obj['object']}: {obj.get('prompt', '')}"
        for obj in scene_plan
    ])

    return f"""
Refine these 3D generation prompts to be more specific and optimized for 3D printing:

{objects_list}

For each object:
1. Add specific details about dimensions, materials, and structure
2. Include guidance for 3D printability (avoid overhangs, ensure stability)
3. Specify visual style (e.g., "modern minimalist", "organic", "geometric")
4. Keep prompts concise but descriptive

Return the same JSON structure with refined prompts.
"""


def validate_plan_message(scene_plan: List[Dict]) -> str:
    """
    Create message for validating plan

    Args:
        scene_plan: List of objects to validate

    Returns:
        Message string for validation
    """
    objects_list = "\n".join([
        f"- {obj['object']}"
        for obj in scene_plan
    ])

    return f"""
Validate this 3D generation plan:

Objects to generate:
{objects_list}

Check for:
1. Feasibility - can these be 3D printed?
2. Completeness - are all necessary parts included?
3. Dependencies - do objects need to fit together?
4. Potential issues - overhangs, thin walls, support requirements

Respond with:
{{
  "valid": true/false,
  "issues": ["list of potential issues"],
  "suggestions": ["list of suggestions for improvement"]
}}
"""
