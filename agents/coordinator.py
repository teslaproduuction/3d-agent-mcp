"""
Coordinator Agent for orchestrating the full 3D generation workflow
Based on project_enhancements.md specifications
"""
from typing import List, Dict, Optional
from agents.planner_agent import PlannerAgent
from agents.image_generation_agent import ImageGenerationAgent
from agents.generation_agent import GenerationAgent
from agents.intelligent_postprocessing_agent import IntelligentPostProcessingAgent
from api_clients.llm_client import LLMClient
from utils.config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class CoordinatorAgent:
    """
    Orchestrates the full 3D generation workflow:
    Text → Planning → 2D Preview → User Approval → 3D Generation → Intelligent PostProcessing
    """

    def __init__(self, config: Config):
        self.config = config

        # Initialize LLM client
        self.llm_client = LLMClient(
            provider='openai',
            api_key=config.get_api_key('openai'),
            model='gpt-4'
        )

        # Initialize agents
        self.planner = PlannerAgent(llm_client=self.llm_client)

        image_provider = config.image_generation_settings.get('provider', 'dalle3')
        local_image_config = None
        if image_provider == 'local':
            local_image_models = config.get('default_settings.local_image_models', {})
            default_model_name = local_image_models.get('default_model', 'flux-schnell')
            available = local_image_models.get('available_models', [])
            local_image_config = next(
                (m for m in available if m.get('name') == default_model_name), None
            )
        self.image_generator = ImageGenerationAgent(
            provider=image_provider,
            openai_api_key=config.get_api_key('openai'),
            replicate_api_key=config.get('api_keys.replicate'),
            local_model_config=local_image_config
        )

        gen_3d_provider = config.generation_settings.get('api_provider', 'tripo')
        self.generator_3d = GenerationAgent(
            provider=gen_3d_provider,
            api_key=config.get_api_key('tripo') if gen_3d_provider != 'local' else None,
            config=config if gen_3d_provider == 'local' else None
        )

        self.postprocessor = IntelligentPostProcessingAgent(
            llm_client=self.llm_client
        )

        self.conversation_history = []

    async def process_chat_message(self, message: str) -> str:
        """
        Process a chat message from the user

        Args:
            message: User's message

        Returns:
            Agent's response
        """
        self.conversation_history.append({
            'role': 'user',
            'content': message
        })

        response = await self.planner.process_user_message(
            message,
            self.conversation_history
        )

        self.conversation_history.append({
            'role': 'assistant',
            'content': response
        })

        return response

    async def get_scene_plan(self, chat_history: List[Dict]) -> List[Dict]:
        """
        Extract scene plan from chat history

        Args:
            chat_history: Gradio chatbot history format [{"role": "user", "content": "..."}, ...]

        Returns:
            List of object specifications
        """
        # Combine all user messages
        user_messages = []
        for msg in chat_history:
            if msg.get('role') == 'user':
                content = msg['content']
                # Handle different content formats (string or list)
                if isinstance(content, list):
                    # If content is a list, extract text from it
                    # Gradio can send content as list of dicts with 'text' key
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and 'text' in item:
                            text_parts.append(item['text'])
                        elif isinstance(item, str):
                            text_parts.append(item)
                        else:
                            text_parts.append(str(item))
                    content = ' '.join(text_parts)
                elif not isinstance(content, str):
                    content = str(content)
                user_messages.append(content)

        combined_request = " ".join(user_messages)

        logger.info(f"Extracting scene plan from: {combined_request}")

        scene_plan = await self.planner.plan_scene(combined_request)
        return scene_plan

    async def execute_generation(
        self,
        scene_plan: List[Dict],
        config: Dict,
        generate_previews: bool = True
    ) -> List[Dict]:
        """
        Execute the full generation workflow

        Workflow:
        1. Planner: Refine prompts
        2. Image Generation: Create 2D previews (if enabled)
        3. 3D Generation: Create models (text-to-3D or image-to-3D)
        4. Intelligent Post-Processing: Prepare for printing

        Args:
            scene_plan: List of objects to generate
            config: Generation configuration
            generate_previews: Whether to generate 2D previews first

        Returns:
            List of processed results
        """
        logger.info(f"Starting generation workflow for {len(scene_plan)} objects")

        # 1. PLANNER: Refine prompts
        logger.info("Step 1: Refining prompts...")
        refined_prompts = await self.planner.refine_prompts(scene_plan)

        # 2. IMAGE GENERATION: Create 2D previews
        image_previews = []
        if generate_previews and config.get('image_generation', {}).get('enabled', True):
            logger.info("Step 2: Generating 2D previews...")
            for i, prompt_data in enumerate(refined_prompts):
                try:
                    logger.debug(f"Prompt data {i}: {prompt_data}")
                    logger.debug(f"Prompt type: {type(prompt_data['prompt'])}")
                    logger.debug(f"Prompt value: {prompt_data['prompt']}")

                    preview = await self.image_generator.generate_preview(
                        prompt=prompt_data['prompt'],
                        style=config.get('image_generation', {}).get('style', 'realistic 3D render')
                    )
                    logger.debug(f"Preview result: {preview}")
                    prompt_data['preview_image'] = preview['image_path']
                    image_previews.append(preview)
                    logger.info(f"Preview generated: {preview['image_path']}")
                    print(f"[OK] Preview {i} generated: {preview['image_path']}")
                except Exception as e:
                    import traceback
                    logger.error(f"Failed to generate preview {i}: {e}")
                    logger.error(f"Full traceback:\n{traceback.format_exc()}")
                    print(f"Preview generation error for {i}: {e}")
                    print(f"Full traceback:\n{traceback.format_exc()}")
                    prompt_data['preview_image'] = None
                    image_previews.append(None)
        else:
            logger.info("Step 2: Skipping 2D preview generation")

        # 2.5. USER APPROVAL would happen here in the UI
        # For now, we proceed with all objects

        # 3. 3D GENERATION: Create models
        logger.info("Step 3: Generating 3D models...")
        use_image_to_3d = config.get('use_image_to_3d', True)

        logger.debug(f"Refined prompts for 3D generation: {refined_prompts}")
        logger.debug(f"use_image_to_3d: {use_image_to_3d}")
        logger.debug(f"Default parameters: {self.generator_3d.get_default_parameters()}")

        raw_models = await self.generator_3d.generate_batch(
            prompts=refined_prompts,
            use_image_to_3d=use_image_to_3d,
            **self.generator_3d.get_default_parameters()
        )

        logger.debug(f"Raw models result: {raw_models}")

        # 4. INTELLIGENT POST-PROCESSING: Prepare for printing
        logger.info("Step 4: Intelligent post-processing...")
        processed_results = []

        for i, model_result in enumerate(raw_models):
            if 'error' in model_result:
                logger.error(f"Skipping model {i} due to generation error")
                # Add 2D preview even if 3D generation failed
                if image_previews and i < len(image_previews) and image_previews[i]:
                    model_result['2d_preview'] = image_previews[i]['image_path']
                    logger.info(f"Added 2D preview to failed model {i}: {image_previews[i]['image_path']}")
                processed_results.append(model_result)
                continue

            if config['postprocessing'].get('enabled', True):
                try:
                    result = await self.postprocessor.process_intelligently(
                        input_file=model_result['model_path'],
                        object_name=refined_prompts[i]['object'],
                        user_preferences=config['postprocessing']
                    )

                    # Add preview image from 2D generation
                    if image_previews and i < len(image_previews) and image_previews[i]:
                        result['2d_preview'] = image_previews[i]['image_path']

                    processed_results.append(result)
                    logger.info(f"Model {i} processed successfully")

                except Exception as e:
                    logger.error(f"Post-processing failed for model {i}: {e}")
                    processed_results.append({
                        'error': str(e),
                        'model_file': model_result.get('model_path'),
                        'object_name': refined_prompts[i]['object']
                    })
            else:
                # No post-processing, return raw model
                processed_results.append({
                    'object_name': refined_prompts[i]['object'],
                    'model_file': model_result['model_path'],
                    '2d_preview': image_previews[i]['image_path'] if image_previews and i < len(image_previews) and image_previews[i] else None,
                    'metadata': model_result.get('metadata', {}),
                    'analysis': None,
                    'decisions': None,
                    'reasoning': "Post-processing disabled by user"
                })

        logger.info(f"Workflow complete: {len(processed_results)} models processed")
        return processed_results

    async def generate_single_quick(
        self,
        prompt: str,
        skip_preview: bool = False,
        skip_postprocessing: bool = False
    ) -> Dict:
        """
        Quick generation of a single object

        Args:
            prompt: Text description
            skip_preview: Skip 2D preview generation
            skip_postprocessing: Skip intelligent post-processing

        Returns:
            Processed result
        """
        logger.info(f"Quick generation: {prompt}")

        # Create simple plan
        scene_plan = [{
            'object': 'object',
            'prompt': prompt,
            'priority': 1
        }]

        # Config for quick generation
        config = {
            'image_generation': {
                'enabled': not skip_preview,
                'style': 'realistic 3D render'
            },
            'use_image_to_3d': not skip_preview,
            'postprocessing': {
                'enabled': not skip_postprocessing,
                'auto_orient': True,
                'generate_supports': True,
                'max_overhang_angle': 45.0
            }
        }

        results = await self.execute_generation(
            scene_plan,
            config,
            generate_previews=not skip_preview
        )

        return results[0] if results else None

    async def validate_and_plan(self, user_request: str) -> Dict:
        """
        Create and validate a generation plan

        Args:
            user_request: User's description

        Returns:
            Plan with validation info
        """
        # Create plan
        scene_plan = await self.planner.plan_scene(user_request)

        # Validate
        validation = await self.planner.validate_plan(scene_plan)

        return {
            'scene_plan': scene_plan,
            'validation': validation
        }

    def __repr__(self):
        return (
            f"CoordinatorAgent("
            f"planner={self.planner}, "
            f"image_gen={self.image_generator}, "
            f"3d_gen={self.generator_3d}, "
            f"postprocessor={self.postprocessor})"
        )
