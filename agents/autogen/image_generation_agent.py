"""
AutoGen Image Generation Agent for creating 2D previews
Uses ConversableAgent with function calling
"""
from autogen import ConversableAgent
from typing import List, Dict
from agents.image_generation_agent import ImageGenerationAgent as LegacyImageAgent
from utils.logger import get_logger

logger = get_logger(__name__)


IMAGE_GEN_SYSTEM_MESSAGE = """
You generate 2D preview images for 3D objects using image generation APIs.

Your role:
1. Receive object descriptions and prompts
2. Use the generate_image_preview function to create 2D previews
3. Return image paths for successful generations
4. Report any errors clearly

Guidelines:
- Enhance prompts to emphasize 3D render style, product photography
- Add details like "white background", "studio lighting", "isometric view"
- Keep track of which objects have previews generated

Be concise in your responses.
"""


def create_image_generation_agent(
    config_list: List[Dict],
    image_api_client: LegacyImageAgent,
    **kwargs
) -> ConversableAgent:
    """
    Create AutoGen Image Generation Agent

    Args:
        config_list: List of LLM configurations
        image_api_client: Instance of ImageGenerationAgent for actual generation
        **kwargs: Additional arguments for ConversableAgent

    Returns:
        ConversableAgent configured for image generation
    """
    logger.info("Creating AutoGen Image Generation Agent")

    # Function definitions for AutoGen
    async def generate_image_preview(
        prompt: str,
        style: str = "realistic 3D render, product design"
    ) -> Dict:
        """
        Generate 2D preview image

        Args:
            prompt: Description of the object
            style: Visual style for the image

        Returns:
            Dict with image_path and metadata
        """
        try:
            logger.info(f"Generating image preview: {prompt[:50]}...")
            result = await image_api_client.generate_preview(prompt, style)
            logger.info(f"Image generated: {result.get('image_path')}")
            return result
        except Exception as e:
            logger.error(f"Failed to generate image: {e}")
            return {"error": str(e)}

    # Function schema for AutoGen
    function_schema = {
        "name": "generate_image_preview",
        "description": "Generate a 2D preview image for a 3D object using DALL-E 3, SDXL, or Flux",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description of the object to generate"
                },
                "style": {
                    "type": "string",
                    "description": "Visual style (e.g., 'realistic 3D render, product design')",
                    "default": "realistic 3D render, product design"
                }
            },
            "required": ["prompt"]
        }
    }

    agent = ConversableAgent(
        name="image_generator",
        system_message=IMAGE_GEN_SYSTEM_MESSAGE,
        llm_config={
            "config_list": config_list,
            "temperature": 0.5,
            "timeout": 120,
            "functions": [function_schema],
        },
        function_map={
            "generate_image_preview": generate_image_preview
        },
        human_input_mode="NEVER",
        max_consecutive_auto_reply=10,
        **kwargs
    )

    logger.info("Image Generation Agent created successfully")
    return agent


def create_batch_generation_message(prompts_data: List[Dict]) -> str:
    """
    Create message for batch image generation

    Args:
        prompts_data: List of objects with prompts

    Returns:
        Message string for agent
    """
    objects_list = "\n".join([
        f"{i+1}. {obj['object']}: {obj.get('prompt', '')}"
        for i, obj in enumerate(prompts_data)
    ])

    return f"""
Generate 2D preview images for these objects:

{objects_list}

For each object:
1. Use generate_image_preview function
2. Enhance the prompt for better 3D visualization
3. Use style: "realistic 3D render, product photography, white background, studio lighting"

Generate previews for all objects and report the results.
"""
