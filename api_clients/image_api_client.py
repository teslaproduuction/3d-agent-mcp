"""
Image generation API client for DALL-E 3, SDXL, Flux, and Local Models
"""
from typing import Literal, Dict, Optional
from openai import AsyncOpenAI
import replicate
import aiohttp
from pathlib import Path
import uuid


class ImageAPIClient:
    """
    Client for image generation APIs
    Supports: DALL-E 3, GPT-Image-1.5, SDXL (Replicate), Flux (Replicate), Local Models (Qwen-Image-Edit)
    """

    def __init__(
        self,
        provider: Literal['dalle3', 'gpt-image-1.5', 'sdxl', 'flux', 'local'] = 'dalle3',
        openai_api_key: Optional[str] = None,
        replicate_api_key: Optional[str] = None,
        local_model_config: Optional[Dict] = None
    ):
        self.provider = provider

        if provider in ['dalle3', 'gpt-image-1.5']:
            if not openai_api_key:
                raise ValueError(f"OpenAI API key required for {provider}")
            self.client = AsyncOpenAI(api_key=openai_api_key)

        elif provider in ['sdxl', 'flux']:
            if not replicate_api_key:
                raise ValueError(f"Replicate API key required for {provider.upper()}")
            self.replicate_client = replicate.Client(api_token=replicate_api_key)

        elif provider == 'local':
            if not local_model_config:
                raise ValueError("Local model configuration required for local provider")

            self._local_mode = local_model_config.get('mode', 'api')
            if self._local_mode == 'comfyui':
                from api_clients.comfyui_client import ComfyUIClient
                self.local_client = ComfyUIClient(
                    base_url=local_model_config.get('docker_url', 'http://localhost:8188'),
                    ckpt_name=local_model_config.get('ckpt_name', 'flux1-schnell-fp8.safetensors')
                )
            else:
                from api_clients.local_image_client import LocalImageClient
                self.local_client = LocalImageClient(
                    model_name=local_model_config.get('model_name', 'qwen-image-edit'),
                    docker_url=local_model_config.get('docker_url', 'http://localhost:8001'),
                    api_endpoint=local_model_config.get('api_endpoint', '/api/generate'),
                    device=local_model_config.get('device', 'cuda'),
                    use_half_precision=local_model_config.get('use_half_precision', True)
                )

    async def generate(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        style: str = "realistic 3D render",
        size: str = "1024x1024"
    ) -> Dict:
        """
        Generate image from text prompt

        Args:
            prompt: Text description of the image
            negative_prompt: What to avoid (SDXL/Flux/Local only)
            style: Visual style to apply
            size: Image dimensions

        Returns:
            Dict with 'image_path', 'image_url', 'prompt_used', 'provider'
        """
        # Enhance prompt for 3D-suitable output (except for local models that handle it themselves)
        if self.provider != 'local':
            enhanced_prompt = self._enhance_prompt_for_3d(prompt, style)
        else:
            enhanced_prompt = f"{prompt}, {style}"

        if self.provider == 'dalle3':
            return await self._generate_dalle3(enhanced_prompt, size)
        elif self.provider == 'gpt-image-1.5':
            return await self._generate_gpt_image_1_5(enhanced_prompt, size)
        elif self.provider == 'sdxl':
            return await self._generate_sdxl(enhanced_prompt, negative_prompt)
        elif self.provider == 'flux':
            return await self._generate_flux(enhanced_prompt)
        elif self.provider == 'local':
            return await self._generate_local(enhanced_prompt, negative_prompt, size)

    def _enhance_prompt_for_3d(self, prompt: str, style: str) -> str:
        """
        Optimize prompt for 3D-suitable images
        """
        from utils.logger import get_logger
        logger = get_logger(__name__)

        logger.debug(f"_enhance_prompt_for_3d called with prompt type: {type(prompt)}, style type: {type(style)}")
        logger.debug(f"prompt value: {prompt}")
        logger.debug(f"style value: {style}")

        # Ensure prompt and style are strings
        if isinstance(prompt, list):
            logger.warning(f"Prompt is a list, converting: {prompt}")
            prompt = ' '.join(str(item) for item in prompt)
        elif not isinstance(prompt, str):
            logger.warning(f"Prompt is {type(prompt)}, converting: {prompt}")
            prompt = str(prompt)

        if isinstance(style, list):
            logger.warning(f"Style is a list, converting: {style}")
            style = ' '.join(str(item) for item in style)
        elif not isinstance(style, str):
            logger.warning(f"Style is {type(style)}, converting: {style}")
            style = str(style)

        enhancements = [
            "professional product photography",
            "clean white background",
            "studio lighting",
            "centered composition",
            "isometric view",
            style
        ]

        logger.debug(f"enhancements list: {enhancements}")
        logger.debug(f"enhancements types: {[type(e) for e in enhancements]}")

        try:
            result = f"{prompt}, {', '.join(enhancements)}"
            logger.debug(f"Enhanced prompt: {result}")
            return result
        except Exception as e:
            logger.error(f"Error in _enhance_prompt_for_3d: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    async def _generate_dalle3(self, prompt: str, size: str) -> Dict:
        """Generate using DALL-E 3"""
        response = await self.client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality="hd",  # Options: 'standard' or 'hd'
            n=1
        )

        image_url = response.data[0].url
        revised_prompt = response.data[0].revised_prompt

        # Download image
        image_path = await self._download_image(image_url)

        return {
            'image_path': str(image_path),
            'image_url': image_url,
            'prompt_used': revised_prompt,
            'provider': 'dalle3'
        }

    async def _generate_gpt_image_1_5(self, prompt: str, size: str) -> Dict:
        """Generate using GPT-Image-1.5"""
        response = await self.client.images.generate(
            model="gpt-image-1.5",
            prompt=prompt,
            size=size,
            quality="hd",  # Options: 'standard' or 'hd'
            n=1
        )

        image_url = response.data[0].url
        # GPT-Image-1.5 may also have revised_prompt
        revised_prompt = getattr(response.data[0], 'revised_prompt', prompt)

        # Download image
        image_path = await self._download_image(image_url)

        return {
            'image_path': str(image_path),
            'image_url': image_url,
            'prompt_used': revised_prompt,
            'provider': 'gpt-image-1.5'
        }

    async def _generate_gpt_image_1_5_edit(
        self,
        base_image_path: str,
        prompt: str,
        view_description: str
    ) -> Dict:
        """
        Generate view using GPT-Image-1.5 Edit API
        Uses image editing to change viewing angle while preserving object
        """
        from PIL import Image
        import io

        # Load and prepare base image
        img = Image.open(base_image_path)

        # Resize to 1024x1024 if needed
        if img.size != (1024, 1024):
            img = img.resize((1024, 1024), Image.Resampling.LANCZOS)

        # Convert to RGBA
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # Save image to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        # Create a mask that allows editing of the entire image
        # (fully transparent = area to edit)
        mask = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
        mask_bytes = io.BytesIO()
        mask.save(mask_bytes, format='PNG')
        mask_bytes.seek(0)

        # Edit instruction prompt
        edit_prompt = (
            f"Transform this object to show it from a {view_description}. "
            f"Keep the exact same object, style, colors, materials, and lighting. "
            f"Only change the viewing angle. Maintain product photography quality."
        )

        # Use GPT-Image-1.5 Edit API
        response = await self.client.images.edit(
            model="gpt-image-1.5",
            image=img_bytes,
            mask=mask_bytes,
            prompt=edit_prompt,
            n=1,
            size="1024x1024"
        )

        image_url = response.data[0].url
        image_path = await self._download_image(image_url)

        return {
            'image_path': str(image_path),
            'image_url': image_url,
            'view': view_description,
            'prompt_used': edit_prompt,
            'provider': 'gpt-image-1.5-edit'
        }

    async def _generate_sdxl(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None
    ) -> Dict:
        """Generate using Stable Diffusion XL via Replicate"""
        if negative_prompt is None:
            negative_prompt = (
                "blurry, bad quality, distorted, ugly, "
                "multiple objects, cluttered background"
            )

        # Run model synchronously (replicate client doesn't support async yet)
        import asyncio
        output = await asyncio.to_thread(
            self.replicate_client.run,
            "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
            input={
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "num_inference_steps": 50,
                "guidance_scale": 7.5,
                "width": 1024,
                "height": 1024
            }
        )

        # output is a list of URLs
        image_url = output[0]
        image_path = await self._download_image(image_url)

        return {
            'image_path': str(image_path),
            'image_url': image_url,
            'prompt_used': prompt,
            'provider': 'sdxl'
        }

    async def _generate_flux(self, prompt: str) -> Dict:
        """Generate using Flux Schnell via Replicate"""
        import asyncio
        output = await asyncio.to_thread(
            self.replicate_client.run,
            "black-forest-labs/flux-schnell",
            input={
                "prompt": prompt,
                "num_inference_steps": 4,  # Fast generation
                "aspect_ratio": "1:1"
            }
        )

        image_url = output[0]
        image_path = await self._download_image(image_url)

        return {
            'image_path': str(image_path),
            'image_url': image_url,
            'prompt_used': prompt,
            'provider': 'flux'
        }

    async def _generate_local(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        size: str = "1024x1024"
    ) -> Dict:
        """
        Generate using local model (e.g., Qwen-Image-Edit)

        Args:
            prompt: Enhanced prompt
            negative_prompt: Negative prompt
            size: Image size

        Returns:
            Dict with image info
        """
        from utils.logger import get_logger
        logger = get_logger(__name__)

        if self._local_mode == 'comfyui':
            logger.info("Generating with ComfyUI (FLUX.1-schnell)")
            result = await self.local_client.generate(prompt=prompt, size=size)
            # Save base64 image to file
            image_b64 = result.get('image_base64')
            if image_b64:
                import base64
                filename = f"preview_{uuid.uuid4().hex[:8]}.png"
                filepath = Path("outputs/previews") / filename
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_bytes(base64.b64decode(image_b64))
                result['image_path'] = str(filepath)
            result['provider'] = 'flux-schnell-comfyui'
            return result
        else:
            logger.info(f"Generating with local model: {self.local_client.model_name}")
            return await self.local_client.generate(
                prompt=prompt,
                negative_prompt=negative_prompt,
                size=size,
                num_inference_steps=20,
                guidance_scale=7.5
            )

    async def generate_view_from_image(
        self,
        base_image_path: str,
        view_description: str,
        original_prompt: str
    ) -> Dict:
        """
        Generate a different view of an object from base image
        Uses image-to-image generation

        Args:
            base_image_path: Path to the base image
            view_description: View angle (e.g., "back view", "left side view")
            original_prompt: Original object description

        Returns:
            Dict with image_path, image_url, view, provider
        """
        # Map view description to precise camera instruction
        view_camera_map = {
            "back view": "rear view, seen from behind, rotated 180 degrees",
            "left side view": "left side profile view, rotated 90 degrees to the left",
            "right side view": "right side profile view, rotated 90 degrees to the right",
            "front view": "front view, facing the camera directly",
            "top view": "top-down view, bird's eye perspective",
            "bottom view": "bottom view, seen from below",
        }
        camera_instruction = view_camera_map.get(view_description, view_description)
        prompt = (
            f"{original_prompt}, {camera_instruction}, "
            f"same object same style same materials same lighting black background, "
            f"product photography studio render"
        )

        if self.provider == 'dalle3':
            # DALL-E 3 doesn't support img2img directly, use edit API
            return await self._generate_dalle3_variation(base_image_path, prompt, view_description)
        elif self.provider == 'gpt-image-1.5':
            # GPT-Image-1.5 supports image editing
            return await self._generate_gpt_image_1_5_edit(base_image_path, prompt, view_description)
        elif self.provider == 'sdxl':
            return await self._generate_sdxl_img2img(base_image_path, prompt, view_description)
        elif self.provider == 'flux':
            return await self._generate_flux_img2img(base_image_path, prompt, view_description)
        elif self.provider == 'local':
            return await self._generate_local_view(base_image_path, prompt, view_description)

    async def _generate_dalle3_variation(
        self,
        base_image_path: str,
        prompt: str,
        view_description: str
    ) -> Dict:
        """
        Use DALL-E image editing API to generate variations
        Note: DALL-E 3 doesn't support variations, so we use DALL-E 2 for this
        """
        from PIL import Image
        import io

        # DALL-E variations requires PNG format and specific size
        # Convert image to proper format
        img = Image.open(base_image_path)

        # Resize to 1024x1024 if needed (DALL-E 2 requirement)
        if img.size != (1024, 1024):
            img = img.resize((1024, 1024), Image.Resampling.LANCZOS)

        # Convert to RGBA if needed
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # Save to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        # Use DALL-E 2 variations (it actually uses the image)
        response = await self.client.images.create_variation(
            image=img_bytes,
            n=1,
            size="1024x1024",
            model="dall-e-2"  # DALL-E 2 supports variations
        )

        image_url = response.data[0].url
        image_path = await self._download_image(image_url)

        return {
            'image_path': str(image_path),
            'image_url': image_url,
            'view': view_description,
            'prompt_used': f"Variation of original: {prompt}",
            'provider': 'dalle2-variation'
        }

    async def _generate_sdxl_img2img(
        self,
        base_image_path: str,
        prompt: str,
        view_description: str
    ) -> Dict:
        """Generate view using SDXL img2img"""
        import asyncio

        # Read base image as URL or convert to data URI
        with open(base_image_path, 'rb') as f:
            image_data = f.read()

        # Upload to temporary hosting or use replicate's image input
        # For now, use direct file upload
        output = await asyncio.to_thread(
            self.replicate_client.run,
            "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
            input={
                "prompt": prompt,
                "image": open(base_image_path, 'rb'),
                "prompt_strength": 0.5,  # Lower = more similar to original (0.5 for better consistency)
                "num_inference_steps": 50,
                "guidance_scale": 9.0,  # Higher guidance for more prompt adherence
                "scheduler": "DPMSolverMultistep"  # Better quality
            }
        )

        image_url = output[0]
        image_path = await self._download_image(image_url)

        return {
            'image_path': str(image_path),
            'image_url': image_url,
            'view': view_description,
            'prompt_used': prompt,
            'provider': 'sdxl'
        }

    async def _generate_flux_img2img(
        self,
        base_image_path: str,
        prompt: str,
        view_description: str
    ) -> Dict:
        """
        Flux Schnell doesn't support img2img natively,
        so we'll generate a new image with view prompt
        """
        result = await self._generate_flux(f"{prompt}, {view_description}")
        result['view'] = view_description
        return result

    async def _generate_local_view(
        self,
        base_image_path: str,
        prompt: str,
        view_description: str
    ) -> Dict:
        """
        Generate view using local model's image editing capability

        Args:
            base_image_path: Base image path
            prompt: Full prompt
            view_description: View description

        Returns:
            Dict with image info
        """
        from utils.logger import get_logger
        logger = get_logger(__name__)

        logger.info(f"Generating {view_description} using local model")

        if self._local_mode == 'comfyui':
            # Use Zero123Plus for proper 3D-aware view generation
            views = await self.local_client.generate_multiview(
                image_path=base_image_path,
                inference_steps=35,
            )
            # Pick the view closest to what was requested
            view_index_map = {
                "back view": 2, "right side view": 1, "left side view": 4,
                "front view": 0, "top view": 3, "bottom view": 5,
            }
            idx = view_index_map.get(view_description, 1)
            if idx >= len(views):
                idx = 0
            image_b64, view_name = views[idx]
            import base64
            image_bytes = base64.b64decode(image_b64)
            view_slug = view_name.lower().replace(" ", "-")
            filename = f"zero123_{view_slug}_{uuid.uuid4().hex[:8]}.png"

            flux_filepath = Path("outputs/flux") / filename
            flux_filepath.parent.mkdir(parents=True, exist_ok=True)
            flux_filepath.write_bytes(image_bytes)

            preview_filepath = Path("outputs/previews") / filename
            preview_filepath.parent.mkdir(parents=True, exist_ok=True)
            preview_filepath.write_bytes(image_bytes)

            result = {
                "image_path": str(preview_filepath),
                "flux_image_path": str(flux_filepath),
                "image_base64": image_b64,
                "view": view_description,
                "provider": "zero123plus",
            }
        else:
            result = await self.local_client.edit_image(
                base_image_path=base_image_path,
                edit_prompt=prompt,
                strength=0.6,
                guidance_scale=7.5
            )
            result['view'] = view_description

        return result

    async def img2img_edit(
        self,
        image_path: str,
        prompt: str,
        denoise: float = 0.70,
    ) -> Dict:
        """
        Edit an existing image with a text prompt using img2img.

        For local/comfyui: FLUX img2img with denoise strength.
        For gpt-image-1.5: GPT image edit API (no mask = full edit).
        Falls back to txt2img for providers without img2img support.

        denoise: 0.4 = subtle edit, 0.7 = moderate, 1.0 = full regen
        """
        from utils.logger import get_logger
        _log = get_logger(__name__)
        _log.info(f"img2img_edit provider={self.provider} denoise={denoise} prompt={prompt[:80]}")

        if self.provider == 'local':
            if self._local_mode == 'comfyui':
                result = await self.local_client.img2img(
                    image_path=image_path,
                    prompt=prompt,
                    denoise=denoise,
                )
                # img2img returns base64, save to outputs/previews
                image_b64 = result.get('image_base64', '')
                if image_b64:
                    import base64
                    filename = result.get('image_path', f"i2i_{uuid.uuid4().hex[:8]}.png")
                    if not filename.startswith("outputs"):
                        filename = f"i2i_{uuid.uuid4().hex[:8]}.png"
                    filepath = Path("outputs/previews") / Path(filename).name
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    filepath.write_bytes(base64.b64decode(image_b64))
                    result['image_path'] = str(filepath)
                return result
            else:
                # Other local modes: fall through to txt2img
                pass

        elif self.provider == 'gpt-image-1.5':
            return await self._generate_gpt_image_1_5_edit(image_path, prompt, "edit")

        # Fallback: txt2img (no img2img support for this provider)
        _log.warning(f"img2img_edit fallback to txt2img for provider={self.provider}")
        return await self.generate(prompt=prompt)

    async def _download_image(self, url: str) -> Path:
        """Download image from URL"""
        filename = f"preview_{uuid.uuid4().hex[:8]}.png"
        filepath = Path("outputs/previews") / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.read()
                    filepath.write_bytes(content)
                    return filepath

        raise Exception(f"Failed to download image from {url}")

    def __repr__(self):
        return f"ImageAPIClient(provider='{self.provider}')"
