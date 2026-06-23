"""
AutoGen Coordinator for orchestrating 3D generation workflow
Uses GroupChat to coordinate multiple agents
"""
from typing import List, Dict, Optional
import json

from autogen import GroupChat, GroupChatManager
from autogen.agentchat import Agent

from agents.autogen.planner_agent import create_planner_agent
from agents.autogen.image_generation_agent import create_image_generation_agent
from agents.autogen.generation_3d_agent import create_generation_3d_agent
from agents.autogen.postprocessing_agent import (
    create_postprocessing_agent,
    process_model_intelligently
)
from agents.autogen.verification_agent import (
    create_verification_agent,
    create_verification_message
)

from agents.image_generation_agent import ImageGenerationAgent
from agents.generation_agent import GenerationAgent
from api_clients.llm_client import LLMClient
from api_clients.autogen_llm_config import AutoGenLLMConfig
from utils.config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class AutoGenCoordinator:
    """
    Coordinator for AutoGen-based 3D generation workflow
    Orchestrates multiple agents through GroupChat
    """

    def __init__(self, config: Config):
        """
        Initialize AutoGen Coordinator

        Args:
            config: Configuration object
        """
        self.config = config
        logger.info("Initializing AutoGenCoordinator")

        # Build LLM config list
        llm_config_builder = AutoGenLLMConfig(config)
        self.config_list = llm_config_builder.build_config_list()

        # Initialize API clients for legacy functionality
        llm_provider = config.get('llm.default_provider', 'openai')
        if llm_provider == 'ollama':
            ollama_url = config.get('llm.local.ollama_base_url', 'http://localhost:11434/v1')
            ollama_model = (config.get('llm.local.ollama_models') or ['qwen2.5:7b'])[0]
            self.llm_client = LLMClient(
                provider='openai', api_key='ollama',
                model=ollama_model, base_url=ollama_url
            )
        else:
            self.llm_client = LLMClient(
                provider=llm_provider,
                api_key=config.get_api_key('openai'),
                model=config.get('llm.cloud.openai.model', 'gpt-4')
            )

        image_provider = config.image_generation_settings.get('provider', 'dalle3')
        local_image_config = None
        if image_provider == 'local':
            local_image_models = config.get('default_settings.local_image_models', {})
            default_model_name = local_image_models.get('default_model', 'flux-schnell')
            available = local_image_models.get('available_models', [])
            local_image_config = next(
                (m for m in available if m.get('name') == default_model_name), None
            )
        self.image_api_client = ImageGenerationAgent(
            provider=image_provider,
            openai_api_key=config.get_api_key('openai'),
            replicate_api_key=config.get('api_keys.replicate'),
            local_model_config=local_image_config
        )

        gen_3d_provider = config.generation_settings.get('api_provider', 'tripo')
        self.gen_3d_client = GenerationAgent(
            provider=gen_3d_provider,
            api_key=config.get_api_key('tripo') if gen_3d_provider != 'local' else None,
            config=config if gen_3d_provider == 'local' else None
        )

        # Create AutoGen agents
        self.planner = create_planner_agent(self.config_list)
        self.image_gen = create_image_generation_agent(
            self.config_list,
            self.image_api_client
        )
        self.gen_3d = create_generation_3d_agent(
            self.config_list,
            self.gen_3d_client
        )
        self.postprocessor = create_postprocessing_agent(
            self.config_list,
            self.llm_client,
            config.get('orientation_analysis', {})
        )
        self.verifier = create_verification_agent(self.config_list)

        # Store conversation history
        self.conversation_history = []

        logger.info("AutoGenCoordinator initialized successfully")

    async def process_chat_message(self, message: str) -> str:
        """
        Process a chat message from the user (for interactive chat)

        Args:
            message: User's message

        Returns:
            Agent's response
        """
        self.conversation_history.append({
            'role': 'user',
            'content': message
        })

        # Use planner for chat response
        response_message = self.planner.generate_reply(
            messages=[{"role": "user", "content": message}]
        )

        response = response_message if isinstance(response_message, str) else str(response_message)

        self.conversation_history.append({
            'role': 'assistant',
            'content': response
        })

        return response

    async def generate_image_prompt(self, user_description: str) -> str:
        """
        Generate optimized image generation prompt from user description

        Args:
            user_description: User's description of what they want

        Returns:
            Optimized prompt for image generation
        """
        system_prompt = """You are an expert at creating prompts for AI image generation.
Your task is to convert user descriptions into detailed, optimized prompts for generating 3D model preview images.

CRITICAL RULES:
1. ALWAYS write the prompt in ENGLISH ONLY — regardless of the input language.
2. Output ONLY the prompt text. No explanations, no translations, no comments, no language notes, no parentheses with meta-text.
3. Do NOT include Chinese, Russian, or any other non-English characters in the output.

Guidelines:
- Focus on clear object description
- Include relevant details about shape, material, and function
- Use terms like "product design", "3D render", "isometric view", "white background", "studio lighting"
- Keep prompts concise but descriptive (1-2 sentences max)
- Avoid abstract concepts, focus on concrete visual elements
- Optimize for clean, centered, professional product photography style"""

        prompt = f"""Convert this description into an English-only image generation prompt: {user_description}

Output only the English prompt, nothing else:"""

        optimized_prompt = await self.llm_client.complete(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=200
        )

        logger.info(f"Generated image prompt: {optimized_prompt}")
        return optimized_prompt.strip()

    async def generate_preview_candidates(
        self,
        prompt: str,
        num_candidates: int = 4,
        style: str = "realistic 3D render, product design"
    ) -> List[Dict]:
        """
        Generate multiple preview image candidates for user to choose from

        Args:
            prompt: Image generation prompt
            num_candidates: Number of images to generate (default: 4)
            style: Visual style

        Returns:
            List of generated image dicts with paths
        """
        import asyncio
        logger.info(f"Generating {num_candidates} preview candidates")

        if not await self._is_local_image_service_healthy():
            error_message = (
                "Локальный сервис генерации изображений недоступен. "
                "Проверьте контейнер ComfyUI и повторите попытку."
            )
            logger.warning(error_message)
            return [
                {
                    'error': error_message,
                    'candidate_index': i,
                    'is_connection_error': True,
                }
                for i in range(num_candidates)
            ]

        is_local_provider = self.image_api_client.provider == 'local'
        max_retries = 2 if is_local_provider else 5
        retry_delay = 2.0 if is_local_provider else 10.0

        results = []
        for i in range(num_candidates):
            result = await self._generate_candidate_with_retry(
                prompt=prompt,
                style=style,
                candidate_index=i,
                max_retries=max_retries,
                retry_delay=retry_delay,
            )
            results.append(result)

            if result.get('error') and result.get('is_connection_error'):
                fail_fast_error = (
                    "Локальный сервис генерации изображений временно недоступен. "
                    "Оставшиеся кандидаты пропущены, чтобы не держать UI в ожидании."
                )
                logger.warning(
                    f"Stopping candidate generation early after connection error on candidate {i + 1}"
                )
                for remaining_index in range(i + 1, num_candidates):
                    results.append(
                        {
                            'error': fail_fast_error,
                            'candidate_index': remaining_index,
                            'is_connection_error': True,
                        }
                    )
                break

        return results

    async def _is_local_image_service_healthy(self) -> bool:
        """Check local image service health when provider is local."""
        if self.image_api_client.provider != 'local':
            return True

        image_api = self.image_api_client.api_client
        local_client = getattr(image_api, 'local_client', None)
        check_health = getattr(local_client, 'check_health', None)

        if callable(check_health):
            try:
                return await check_health()
            except Exception as exc:
                logger.warning(f"Local image health check failed: {exc}")
                return False

        # If client does not expose health check, avoid hard-failing.
        return True

    async def _generate_candidate_with_retry(
        self,
        prompt: str,
        style: str,
        candidate_index: int,
        max_retries: int = 5,
        retry_delay: float = 10.0,
    ) -> dict:
        """Generate one image candidate with retry on connection errors."""
        import asyncio
        last_error = None
        is_connection_error = False
        for attempt in range(1, max_retries + 1):
            try:
                result = await self.image_api_client.generate_preview(
                    prompt=prompt,
                    style=style,
                )
                result['candidate_index'] = candidate_index
                logger.info(f"Generated candidate {candidate_index + 1} (attempt {attempt})")
                return result
            except Exception as e:
                last_error = e
                is_connection_error = any(
                    kw in str(e).lower()
                    for kw in ('connect call failed', 'cannot connect', 'connection refused',
                               'connection reset', 'server disconnected', 'clientconnectorerror',
                               'service unavailable', 'temporarily unavailable',
                               'comfyui unavailable', 'timeout')
                )
                if is_connection_error and attempt < max_retries:
                    wait = retry_delay * attempt
                    logger.warning(
                        f"Candidate {candidate_index + 1}: connection error on attempt {attempt}, "
                        f"retrying in {wait:.0f}s... ({e})"
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        f"Failed to generate candidate {candidate_index + 1} "
                        f"after {attempt} attempt(s): {e}"
                    )
                    break

        return {
            'error': str(last_error),
            'candidate_index': candidate_index,
            'is_connection_error': is_connection_error,
        }

    async def get_scene_plan(self, chat_history: List[Dict]) -> List[Dict]:
        """
        Extract scene plan from chat history

        Args:
            chat_history: Gradio chatbot history

        Returns:
            List of object specifications
        """
        # Combine all user messages
        user_messages = []
        for msg in chat_history:
            if msg.get('role') == 'user':
                content = msg['content']
                if isinstance(content, list):
                    text_parts = [item['text'] if isinstance(item, dict) and 'text' in item else str(item) for item in content]
                    content = ' '.join(text_parts)
                elif not isinstance(content, str):
                    content = str(content)
                user_messages.append(content)

        combined_request = " ".join(user_messages)
        logger.info(f"Extracting scene plan from: {combined_request}")

        # Use planner to decompose
        plan_message = f"""
Analyze this request and break it down into individual 3D objects:

Request: "{combined_request}"

Return a JSON array of objects.
"""

        response = self.planner.generate_reply(
            messages=[{"role": "user", "content": plan_message}]
        )

        # Parse JSON response
        try:
            response_str = response if isinstance(response, str) else str(response)
            # Extract JSON from response
            json_start = response_str.find('[')
            json_end = response_str.rfind(']') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_str[json_start:json_end]
                scene_plan = json.loads(json_str)
                logger.info(f"Extracted {len(scene_plan)} objects from plan")
                return scene_plan
            else:
                logger.error("No JSON array found in planner response")
                return []
        except Exception as e:
            logger.error(f"Failed to parse scene plan: {e}")
            return []

    async def execute_generation(
        self,
        scene_plan: List[Dict],
        config: Dict,
        generate_previews: bool = True
    ) -> List[Dict]:
        """
        Execute the full generation workflow

        Args:
            scene_plan: List of objects to generate
            config: Generation configuration
            generate_previews: Whether to generate 2D previews

        Returns:
            List of processed results
        """
        logger.info(f"Starting AutoGen workflow for {len(scene_plan)} objects")

        processed_results = []

        # Process each object sequentially
        for obj_data in scene_plan:
            try:
                result = await self._process_single_object(
                    obj_data,
                    config,
                    generate_previews
                )
                processed_results.append(result)
            except Exception as e:
                logger.error(f"Failed to process {obj_data.get('object')}: {e}")
                processed_results.append({
                    'error': str(e),
                    'object_name': obj_data.get('object', 'unknown')
                })

        logger.info(f"Workflow complete: {len(processed_results)} results")
        return processed_results

    async def _process_single_object(
        self,
        obj_data: Dict,
        config: Dict,
        generate_preview: bool
    ) -> Dict:
        """Process a single object through the full pipeline"""
        object_name = obj_data['object']
        prompt = obj_data.get('prompt', object_name)

        logger.info(f"Processing: {object_name}")

        # Step 1: Generate 2D preview (if enabled)
        preview_path = None
        if generate_preview and config.get('image_generation', {}).get('enabled', True):
            logger.info(f"Generating 2D preview for {object_name}")
            try:
                preview_result = await self.image_api_client.generate_preview(
                    prompt=prompt,
                    style=config.get('image_generation', {}).get('style', 'realistic 3D render')
                )
                preview_path = preview_result.get('image_path')
                logger.info(f"Preview generated: {preview_path}")
            except Exception as e:
                logger.error(f"Preview generation failed: {e}")

        # Step 2: Generate 3D model
        logger.info(f"Generating 3D model for {object_name}")
        use_image_to_3d = config.get('use_image_to_3d', True) and preview_path

        if use_image_to_3d:
            model_result = await self.gen_3d_client.generate_from_image(
                image_path=preview_path,
                **self.gen_3d_client.get_default_parameters()
            )
        else:
            model_result = await self.gen_3d_client.generate_from_text(
                prompt=prompt,
                **self.gen_3d_client.get_default_parameters()
            )

        if 'error' in model_result:
            raise Exception(model_result['error'])

        model_path = model_result['model_path']
        logger.info(f"3D model generated: {model_path}")

        # Step 3: Intelligent PostProcessing
        if config['postprocessing'].get('enabled', True):
            logger.info(f"Post-processing {object_name}")

            processing_result = await process_model_intelligently(
                input_file=model_path,
                object_name=object_name,
                orientation_config=self.config.get('orientation_analysis', {}),
                llm_client=self.llm_client
            )

            # Step 4: Verification
            logger.info(f"Verifying orientation for {object_name}")
            verification_msg = create_verification_message(processing_result)

            verification_response = self.verifier.generate_reply(
                messages=[{"role": "user", "content": verification_msg}]
            )

            # Add verification to result
            processing_result['verification'] = str(verification_response)
            processing_result['2d_preview'] = preview_path

            logger.info(f"Processing complete for {object_name}")
            return processing_result
        else:
            # No post-processing
            return {
                'object_name': object_name,
                'model_file': model_path,
                '2d_preview': preview_path,
                'metadata': model_result.get('metadata', {}),
                'reasoning': "Post-processing disabled"
            }

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
            skip_postprocessing: Skip post-processing

        Returns:
            Processed result
        """
        logger.info(f"Quick generation: {prompt}")

        scene_plan = [{
            'object': 'object',
            'prompt': prompt,
            'priority': 1
        }]

        config = {
            'image_generation': {
                'enabled': not skip_preview,
                'style': 'realistic 3D render'
            },
            'use_image_to_3d': not skip_preview,
            'postprocessing': {
                'enabled': not skip_postprocessing,
                'auto_orient': True,
                'generate_supports': True
            }
        }

        results = await self.execute_generation(
            scene_plan,
            config,
            generate_previews=not skip_preview
        )

        return results[0] if results else None

    def __repr__(self):
        return (
            f"AutoGenCoordinator("
            f"planner={self.planner.name}, "
            f"image_gen={self.image_gen.name}, "
            f"gen_3d={self.gen_3d.name}, "
            f"postprocessor={self.postprocessor.name}, "
            f"verifier={self.verifier.name})"
        )
