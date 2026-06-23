"""
Image Generation Agent for creating 2D previews before 3D generation
Based on project_enhancements.md specifications
"""
from typing import List, Dict, Literal, Optional
from api_clients.image_api_client import ImageAPIClient


class ImageGenerationAgent:
    """
    Agent for generating 2D preview images
    Supports: DALL-E 3, GPT-Image-1.5, Stable Diffusion XL, Flux
    """

    def __init__(
        self,
        provider: Literal['dalle3', 'gpt-image-1.5', 'sdxl', 'flux', 'local'] = 'gpt-image-1.5',
        openai_api_key: Optional[str] = None,
        replicate_api_key: Optional[str] = None,
        local_model_config: Optional[Dict] = None
    ):
        self.provider = provider
        self.api_client = ImageAPIClient(
            provider=provider,
            openai_api_key=openai_api_key,
            replicate_api_key=replicate_api_key,
            local_model_config=local_model_config
        )

    async def generate_preview(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        style: str = "realistic 3D render, product design",
        size: str = "1024x1024"
    ) -> Dict:
        """
        Generate 2D preview for an object

        Args:
            prompt: Text description of the object
            negative_prompt: What to avoid (for SDXL/Flux)
            style: Visual style
            size: Image dimensions

        Returns:
            Dict with image_path, image_url, prompt_used, provider
        """
        result = await self.api_client.generate(
            prompt=prompt,
            negative_prompt=negative_prompt,
            style=style,
            size=size
        )

        return result

    async def generate_multiple_views(
        self,
        prompt: str,
        views: Optional[List[str]] = None,
        style: str = "realistic 3D render"
    ) -> List[Dict]:
        """
        Generate multiple views of an object
        Useful for multi-view to 3D generation

        Args:
            prompt: Text description of the object
            views: List of view angles (default: front, side, back, top)
            style: Visual style

        Returns:
            List of preview dicts with 'view' field added
        """
        if views is None:
            views = [
                "front view",
                "side view",
                "back view",
                "top view"
            ]

        results = []
        for view in views:
            view_prompt = f"{prompt}, {view}"
            result = await self.generate_preview(
                prompt=view_prompt,
                style=style
            )
            result['view'] = view
            results.append(result)

        return results

    async def generate_batch(
        self,
        prompts: List[str],
        style: str = "realistic 3D render"
    ) -> List[Dict]:
        """
        Generate previews for multiple objects

        Args:
            prompts: List of text descriptions
            style: Visual style for all images

        Returns:
            List of preview dicts
        """
        import asyncio

        tasks = [
            self.generate_preview(prompt=p, style=style)
            for p in prompts
        ]

        results = await asyncio.gather(*tasks)
        return list(results)

    async def regenerate_with_variations(
        self,
        original_prompt: str,
        num_variations: int = 3,
        style: str = "realistic 3D render"
    ) -> List[Dict]:
        """
        Generate multiple variations of the same prompt

        Args:
            original_prompt: Original description
            num_variations: Number of variations to generate
            style: Visual style

        Returns:
            List of preview dicts
        """
        # Add slight variations to prompt
        variation_suffixes = [
            "",  # Original
            ", slightly different angle",
            ", alternative design",
            ", variation",
            ", different perspective"
        ]

        results = []
        for i in range(num_variations):
            suffix = variation_suffixes[i % len(variation_suffixes)]
            prompt = f"{original_prompt}{suffix}"

            result = await self.generate_preview(
                prompt=prompt,
                style=style
            )
            result['variation_index'] = i
            results.append(result)

        return results

    async def generate_multiview_from_image(
        self,
        base_image_path: str,
        original_prompt: str,
        views: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Generate multi-view images from a single base image
        For Tripo3D multiview-to-3d workflow

        Args:
            base_image_path: Path to the front view image
            original_prompt: Original object description
            views: View angles to generate (default: back, left, right)

        Returns:
            List of generated view images with paths
        """
        if views is None:
            views = ["back view", "left side view", "right side view"]

        results = []
        for view in views:
            result = await self.api_client.generate_view_from_image(
                base_image_path=base_image_path,
                view_description=view,
                original_prompt=original_prompt
            )
            results.append(result)

        return results

    async def generate_single(self, prompt: str, style: str = "realistic 3D render") -> Dict:
        """Generate a single image (alias for generate_preview used by UI)"""
        return await self.generate_preview(prompt=prompt, style=style)

    async def img2img_edit(
        self,
        image_path: str,
        prompt: str,
        denoise: float = 0.70,
    ) -> Dict:
        """Edit existing image with text prompt using img2img (FLUX or GPT edit API)."""
        return await self.api_client.img2img_edit(
            image_path=image_path,
            prompt=prompt,
            denoise=denoise,
        )

    def __repr__(self):
        return f"ImageGenerationAgent(provider='{self.provider}')"
