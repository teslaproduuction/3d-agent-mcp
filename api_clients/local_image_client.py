"""
Local Image Generation Client
Supports local models like Qwen-Image-Edit for image generation and editing
"""
from typing import Dict, Optional, List
import aiohttp
import asyncio
from pathlib import Path
import uuid
import base64
from io import BytesIO
from PIL import Image
from utils.logger import get_logger

logger = get_logger(__name__)


class LocalImageClient:
    """
    Client for local image generation models
    Currently supports: Qwen-Image-Edit (via Docker or local deployment)
    """

    def __init__(
        self,
        model_name: str = "qwen-image-edit",
        docker_url: str = "http://localhost:8001",
        api_endpoint: str = "/api/generate",
        device: str = "cuda",
        use_half_precision: bool = True
    ):
        """
        Initialize local image client

        Args:
            model_name: Name of the local model
            docker_url: Base URL for Docker service
            api_endpoint: API endpoint path
            device: Device to use (cuda or cpu)
            use_half_precision: Use FP16 for faster inference
        """
        self.model_name = model_name
        self.docker_url = docker_url.rstrip('/')
        self.api_endpoint = api_endpoint
        self.device = device
        self.use_half_precision = use_half_precision

        logger.info(f"Initialized LocalImageClient with model: {model_name}")
        logger.info(f"Docker URL: {docker_url}")

    async def generate(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        base_image: Optional[str] = None,
        num_inference_steps: int = 20,
        guidance_scale: float = 7.5,
        size: str = "1024x1024"
    ) -> Dict:
        """
        Generate image from text prompt or edit existing image

        Args:
            prompt: Text description
            negative_prompt: What to avoid
            base_image: Optional base image path for editing
            num_inference_steps: Number of diffusion steps
            guidance_scale: How closely to follow the prompt
            size: Image dimensions

        Returns:
            Dict with image_path, image_url, provider, metadata
        """
        try:
            logger.info(f"Generating image with {self.model_name}")
            logger.debug(f"Prompt: {prompt}")

            # Prepare request payload
            payload = {
                "prompt": prompt,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "size": size
            }

            if negative_prompt:
                payload["negative_prompt"] = negative_prompt

            # If base image provided, encode it
            if base_image:
                logger.info(f"Using base image for editing: {base_image}")
                payload["base_image"] = await self._encode_image(base_image)
                payload["editing_mode"] = True

            # Call Docker API
            result = await self._call_docker_api(payload)

            # Save generated image
            output_dir = Path("outputs/previews")
            output_dir.mkdir(parents=True, exist_ok=True)

            image_filename = f"local_{self.model_name}_{uuid.uuid4().hex[:8]}.png"
            image_path = output_dir / image_filename

            # Decode and save image
            image_data = base64.b64decode(result.get("image"))
            image = Image.open(BytesIO(image_data))
            image.save(str(image_path))

            logger.info(f"Image saved to: {image_path}")

            return {
                "image_path": str(image_path),
                "image_url": f"file://{image_path.absolute()}",
                "provider": f"local-{self.model_name}",
                "prompt_used": prompt,
                "metadata": {
                    "model": self.model_name,
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": guidance_scale,
                    "device": self.device,
                    "editing_mode": base_image is not None
                }
            }

        except Exception as e:
            logger.error(f"Failed to generate image with {self.model_name}: {e}")
            raise

    async def generate_multiview(
        self,
        prompt: str,
        base_image: Optional[str] = None,
        views: Optional[List[str]] = None,
        num_inference_steps: int = 20
    ) -> List[Dict]:
        """
        Generate multiple views of an object

        Args:
            prompt: Base prompt
            base_image: Optional base image
            views: List of view descriptions
            num_inference_steps: Number of steps

        Returns:
            List of image result dicts
        """
        if views is None:
            views = ["front view", "back view", "left side view", "right side view"]

        logger.info(f"Generating {len(views)} views")

        results = []
        for view in views:
            view_prompt = f"{prompt}, {view}"
            try:
                result = await self.generate(
                    prompt=view_prompt,
                    base_image=base_image,
                    num_inference_steps=num_inference_steps
                )
                result['view'] = view
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to generate {view}: {e}")
                results.append({
                    'error': str(e),
                    'view': view
                })

        return results

    async def edit_image(
        self,
        base_image_path: str,
        edit_prompt: str,
        strength: float = 0.7,
        guidance_scale: float = 7.5
    ) -> Dict:
        """
        Edit an existing image based on prompt

        Args:
            base_image_path: Path to base image
            edit_prompt: Description of edits
            strength: How much to change (0-1)
            guidance_scale: Prompt adherence

        Returns:
            Dict with edited image info
        """
        logger.info(f"Editing image: {base_image_path}")
        logger.debug(f"Edit prompt: {edit_prompt}")

        payload = {
            "prompt": edit_prompt,
            "base_image": await self._encode_image(base_image_path),
            "editing_mode": True,
            "strength": strength,
            "guidance_scale": guidance_scale
        }

        result = await self._call_docker_api(payload)

        # Save edited image
        output_dir = Path("outputs/previews")
        output_dir.mkdir(parents=True, exist_ok=True)

        image_filename = f"edited_{uuid.uuid4().hex[:8]}.png"
        image_path = output_dir / image_filename

        image_data = base64.b64decode(result.get("image"))
        image = Image.open(BytesIO(image_data))
        image.save(str(image_path))

        logger.info(f"Edited image saved to: {image_path}")

        return {
            "image_path": str(image_path),
            "image_url": f"file://{image_path.absolute()}",
            "provider": f"local-{self.model_name}",
            "prompt_used": edit_prompt,
            "metadata": {
                "model": self.model_name,
                "editing_mode": True,
                "strength": strength,
                "base_image": base_image_path
            }
        }

    async def _call_docker_api(self, payload: Dict) -> Dict:
        """
        Call Docker container API

        Args:
            payload: Request payload

        Returns:
            API response dict

        Raises:
            Exception if API call fails
        """
        url = f"{self.docker_url}{self.api_endpoint}"
        logger.debug(f"Calling Docker API: {url}")

        timeout = aiohttp.ClientTimeout(total=300)  # 5 minutes timeout

        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Docker API error {response.status}: {error_text}")

                    result = await response.json()
                    logger.debug("Docker API call successful")
                    return result

            except aiohttp.ClientError as e:
                logger.error(f"Docker API connection failed: {e}")
                raise Exception(f"Failed to connect to local image model at {url}. "
                               f"Make sure Docker container is running. Error: {e}")

    async def _encode_image(self, image_path: str) -> str:
        """
        Encode image to base64 for API

        Args:
            image_path: Path to image file

        Returns:
            Base64 encoded string
        """
        try:
            image = Image.open(image_path)
            buffered = BytesIO()
            image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            return img_str
        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
            raise

    async def check_health(self) -> bool:
        """
        Check if Docker service is running

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            url = f"{self.docker_url}/health"
            timeout = aiohttp.ClientTimeout(total=5)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    return response.status == 200

        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False


class QwenImageEditClient(LocalImageClient):
    """
    Specialized client for Qwen-Image-Edit model
    Extends LocalImageClient with Qwen-specific features
    """

    def __init__(self, docker_url: str = "http://localhost:8001", **kwargs):
        super().__init__(
            model_name="qwen-image-edit",
            docker_url=docker_url,
            **kwargs
        )

    async def generate_with_reference(
        self,
        prompt: str,
        reference_image: str,
        semantic_control: float = 0.5,
        appearance_control: float = 0.5
    ) -> Dict:
        """
        Generate image with reference for appearance and semantic control
        Unique to Qwen-Image-Edit

        Args:
            prompt: Text description
            reference_image: Reference image path
            semantic_control: Semantic guidance weight (0-1)
            appearance_control: Appearance guidance weight (0-1)

        Returns:
            Generated image dict
        """
        logger.info("Generating with reference image (Qwen-specific)")

        payload = {
            "prompt": prompt,
            "reference_image": await self._encode_image(reference_image),
            "semantic_control": semantic_control,
            "appearance_control": appearance_control,
            "qwen_mode": "reference_guided"
        }

        result = await self._call_docker_api(payload)

        output_dir = Path("outputs/previews")
        output_dir.mkdir(parents=True, exist_ok=True)

        image_filename = f"qwen_ref_{uuid.uuid4().hex[:8]}.png"
        image_path = output_dir / image_filename

        image_data = base64.b64decode(result.get("image"))
        image = Image.open(BytesIO(image_data))
        image.save(str(image_path))

        return {
            "image_path": str(image_path),
            "image_url": f"file://{image_path.absolute()}",
            "provider": "local-qwen-image-edit",
            "prompt_used": prompt,
            "metadata": {
                "model": "qwen-image-edit",
                "reference_guided": True,
                "semantic_control": semantic_control,
                "appearance_control": appearance_control
            }
        }
