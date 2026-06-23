"""
3D Generation Agent for managing 3D model generation APIs
"""
import asyncio
from typing import List, Dict, Literal, Optional
from api_clients.tripo_client import Tripo3DClient
from utils.logger import get_logger

logger = get_logger(__name__)


class GenerationAgent:
    """
    Agent for managing 3D model generation
    Supports: Tripo3D, Local (Hunyuan3D via Docker)
    """

    def __init__(
        self,
        provider: Literal['tripo', 'meshy', 'local'] = 'tripo',
        api_key: Optional[str] = None,
        config=None
    ):
        self.provider = provider

        if provider == 'tripo':
            if not api_key:
                raise ValueError("Tripo3D API key required")
            self.api_client = Tripo3DClient(api_key=api_key)
        elif provider == 'meshy':
            raise NotImplementedError("Meshy integration coming soon")
        elif provider == 'local':
            from api_clients.local_3d_client import Local3DClient
            model_name = 'hunyuan3d'
            if config:
                model_name = config.get('default_settings.local_3d_models.default_model', 'hunyuan3d')
            self.api_client = Local3DClient(model_name=model_name, config=config)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def generate_single(
        self,
        prompt: Optional[str] = None,
        image_path: Optional[str] = None,
        use_image_to_3d: bool = True,
        **kwargs
    ) -> Dict:
        """
        Generate a single 3D model

        Args:
            prompt: Text description (for text-to-3D)
            image_path: Path to image (for image-to-3D)
            use_image_to_3d: Prefer image-to-3D if image available
            **kwargs: Additional generation parameters

        Returns:
            Dict with model_path, metadata
        """
        logger.info(f"Generating 3D model (provider: {self.provider})")

        if image_path and use_image_to_3d:
            logger.info(f"Using image-to-3D with image: {image_path}")
            # Filter out 'pbr' parameter for image_to_3d (not supported)
            image_kwargs = {k: v for k, v in kwargs.items() if k != 'pbr'}
            result = await self.api_client.image_to_3d(
                image_path=image_path,
                **image_kwargs
            )
        elif prompt:
            logger.info(f"Using text-to-3D with prompt: {prompt}")
            result = await self.api_client.text_to_3d(
                prompt=prompt,
                **kwargs
            )
        else:
            raise ValueError("Either prompt or image_path must be provided")

        logger.info(f"Model generated successfully: {result['model_path']}")
        return result

    async def generate_batch(
        self,
        prompts: List[Dict],
        use_image_to_3d: bool = True,
        **kwargs
    ) -> List[Dict]:
        """
        Generate multiple 3D models asynchronously

        Args:
            prompts: List of prompt dicts with 'prompt' and optionally 'preview_image'
            use_image_to_3d: Prefer image-to-3D if preview available
            **kwargs: Additional generation parameters

        Returns:
            List of result dicts
        """
        logger.info(f"Starting batch generation of {len(prompts)} models")

        tasks = []
        for prompt_data in prompts:
            task = self.generate_single(
                prompt=prompt_data.get('prompt'),
                image_path=prompt_data.get('preview_image') if use_image_to_3d else None,
                use_image_to_3d=use_image_to_3d,
                **kwargs
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Model {i} failed: {str(result)}")
                final_results.append({
                    'error': str(result),
                    'prompt_data': prompts[i]
                })
            else:
                final_results.append(result)

        successful = sum(1 for r in final_results if 'error' not in r)
        logger.info(f"Batch generation complete: {successful}/{len(prompts)} successful")

        return final_results

    async def monitor_progress(self, task_ids: List[str]) -> Dict:
        """
        Monitor progress of multiple generation tasks

        Args:
            task_ids: List of task identifiers

        Returns:
            Progress dict with status for each task
        """
        progress = {}

        for task_id in task_ids:
            try:
                status = await self.api_client.get_task_status(task_id)
                progress[task_id] = {
                    'status': status.get('status'),
                    'progress': status.get('progress', 0)
                }
            except Exception as e:
                logger.error(f"Failed to get status for {task_id}: {e}")
                progress[task_id] = {'status': 'error', 'error': str(e)}

        return progress

    async def generate_with_retry(
        self,
        prompt: Optional[str] = None,
        image_path: Optional[str] = None,
        max_retries: int = 3,
        **kwargs
    ) -> Dict:
        """
        Generate with automatic retry on failure

        Args:
            prompt: Text description
            image_path: Path to image
            max_retries: Maximum number of retry attempts
            **kwargs: Additional parameters

        Returns:
            Generation result
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                logger.info(f"Generation attempt {attempt + 1}/{max_retries}")
                result = await self.generate_single(
                    prompt=prompt,
                    image_path=image_path,
                    **kwargs
                )
                return result

            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1} failed: {e}")

                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)

        raise Exception(f"Generation failed after {max_retries} attempts: {last_error}")

    async def generate_from_text(self, prompt: str, **kwargs) -> Dict:
        """
        Generate 3D model from text description

        Args:
            prompt: Text description of the object
            **kwargs: Additional parameters (model_version, face_limit, etc.)

        Returns:
            Dict with model_path, metadata
        """
        params = self.get_default_parameters()
        params.update(kwargs)
        return await self.api_client.text_to_3d(prompt=prompt, **params)

    async def generate_from_image(self, image_path: str, **kwargs) -> Dict:
        """
        Generate 3D model from single image

        Args:
            image_path: Path to input image
            **kwargs: Additional parameters

        Returns:
            Dict with model_path, metadata
        """
        params = self.get_default_parameters()
        params.update(kwargs)
        # Remove 'pbr' for image_to_3d
        if 'pbr' in params:
            del params['pbr']
        return await self.api_client.image_to_3d(image_path=image_path, **params)

    async def generate_from_multiview(self, image_paths: List[str], **kwargs) -> Dict:
        """
        Generate 3D model from multiple view images

        Args:
            image_paths: List of image paths [front, back, left, right]
            **kwargs: Additional parameters

        Returns:
            Dict with model_path, metadata
        """
        params = {
            'model_version': 'v2.5-20250123',  # Multiview requires newer version
            'face_limit': 10000,
            'texture': True,
            'texture_quality': 'standard'
        }
        params.update(kwargs)
        return await self.api_client.multiview_to_3d(image_paths=image_paths, **params)

    def get_default_parameters(self) -> Dict:
        """Get default generation parameters for current provider"""
        if self.provider == 'tripo':
            return {
                'model_version': 'v2.0-20240919',
                'face_limit': 10000,
                'texture': True,
                'pbr': False
            }
        return {}

    def __repr__(self):
        return f"GenerationAgent(provider='{self.provider}')"
