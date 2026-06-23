"""
AutoGen 3D Generation Agent for creating 3D models
Uses ConversableAgent with function calling to Tripo3D API
"""
from autogen import ConversableAgent
from typing import List, Dict
from agents.generation_agent import GenerationAgent as Legacy3DAgent
from utils.logger import get_logger

logger = get_logger(__name__)


GEN_3D_SYSTEM_MESSAGE = """
You generate 3D models using the Tripo3D API.

Your role:
1. Receive object descriptions and optional 2D preview images
2. Use generate_3d_model function to create 3D models
3. Monitor generation progress
4. Return model file paths and metadata

Guidelines:
- Prefer image-to-3D when preview images are available (better quality)
- Use text-to-3D when no preview is available
- Handle generation errors gracefully
- Track progress for long-running generations

Be clear and concise in reporting results.
"""


def create_generation_3d_agent(
    config_list: List[Dict],
    gen_3d_client: Legacy3DAgent,
    **kwargs
) -> ConversableAgent:
    """
    Create AutoGen 3D Generation Agent

    Args:
        config_list: List of LLM configurations
        gen_3d_client: Instance of GenerationAgent for actual 3D generation
        **kwargs: Additional arguments for ConversableAgent

    Returns:
        ConversableAgent configured for 3D generation
    """
    logger.info("Creating AutoGen 3D Generation Agent")

    # Function for 3D generation
    async def generate_3d_model(
        prompt: str,
        image_path: str = None,
        model_version: str = "v2.0-20240919",
        face_limit: int = 10000
    ) -> Dict:
        """
        Generate 3D model from text or image

        Args:
            prompt: Text description of the object
            image_path: Optional path to 2D preview image
            model_version: Tripo3D model version
            face_limit: Maximum number of faces (polygons)

        Returns:
            Dict with model_path and metadata
        """
        try:
            logger.info(f"Generating 3D model: {prompt[:50]}...")
            logger.info(f"Using {'image-to-3D' if image_path else 'text-to-3D'}")

            # Use image-to-3D if image is available
            if image_path:
                result = await gen_3d_client.generate_from_image(
                    image_path=image_path,
                    model_version=model_version,
                    face_limit=face_limit
                )
            else:
                result = await gen_3d_client.generate_from_text(
                    prompt=prompt,
                    model_version=model_version,
                    face_limit=face_limit
                )

            logger.info(f"3D model generated: {result.get('model_path')}")
            return result

        except Exception as e:
            logger.error(f"Failed to generate 3D model: {e}")
            return {"error": str(e)}

    # Function schema
    function_schema = {
        "name": "generate_3d_model",
        "description": "Generate a 3D model using Tripo3D API (text-to-3D or image-to-3D)",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the 3D object"
                },
                "image_path": {
                    "type": "string",
                    "description": "Optional path to 2D preview image for image-to-3D generation"
                },
                "model_version": {
                    "type": "string",
                    "description": "Tripo3D model version",
                    "default": "v2.0-20240919"
                },
                "face_limit": {
                    "type": "integer",
                    "description": "Maximum number of polygons (faces)",
                    "default": 10000
                }
            },
            "required": ["prompt"]
        }
    }

    agent = ConversableAgent(
        name="gen_3d",
        system_message=GEN_3D_SYSTEM_MESSAGE,
        llm_config={
            "config_list": config_list,
            "temperature": 0.3,
            "timeout": 300,  # 5 minutes for 3D generation
            "functions": [function_schema],
        },
        function_map={
            "generate_3d_model": generate_3d_model
        },
        human_input_mode="NEVER",
        max_consecutive_auto_reply=10,
        **kwargs
    )

    logger.info("3D Generation Agent created successfully")
    return agent


def create_batch_generation_message(prompts_data: List[Dict], use_image_to_3d: bool = True) -> str:
    """
    Create message for batch 3D generation

    Args:
        prompts_data: List of objects with prompts and optional preview images
        use_image_to_3d: Whether to use image-to-3D when available

    Returns:
        Message string for agent
    """
    objects_info = []
    for i, obj in enumerate(prompts_data):
        preview_path = obj.get('preview_image')
        has_preview = preview_path and use_image_to_3d

        info = f"{i+1}. {obj['object']}: {obj.get('prompt', '')}"
        if has_preview:
            info += f"\n   Preview image: {preview_path}"

        objects_info.append(info)

    objects_list = "\n".join(objects_info)

    return f"""
Generate 3D models for these objects:

{objects_list}

For each object:
1. Use generate_3d_model function
2. Use image-to-3D if preview image is available (better quality)
3. Otherwise use text-to-3D
4. Use default parameters (model_version='v2.0-20240919', face_limit=10000)

Generate all models and report results including model paths.
"""
