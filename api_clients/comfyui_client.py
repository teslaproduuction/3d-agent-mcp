"""
ComfyUI image generation client for FLUX.1-schnell.
Wraps ComfyUI workflow API into a simple /api/generate-compatible interface.
"""
import asyncio
import base64
import json
import random
import uuid
from pathlib import Path
from typing import Dict, Optional

import aiohttp
from utils.logger import get_logger

logger = get_logger(__name__)

# txt2img workflow
FLUX_TXT2IMG_WORKFLOW = {
    "1": {"inputs": {"ckpt_name": "flux1-schnell-fp8.safetensors"}, "class_type": "CheckpointLoaderSimple"},
    "2": {"inputs": {"text": "PROMPT_PLACEHOLDER", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
    "3": {"inputs": {"text": "", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
    "4": {"inputs": {"width": 1024, "height": 1024, "batch_size": 1}, "class_type": "EmptyLatentImage"},
    "5": {"inputs": {
        "seed": 0, "steps": 4, "cfg": 1.0, "sampler_name": "euler",
        "scheduler": "simple", "denoise": 1.0,
        "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
        "latent_image": ["4", 0]
    }, "class_type": "KSampler"},
    "6": {"inputs": {"samples": ["5", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
    "7": {"inputs": {"filename_prefix": "flux_out", "images": ["6", 0]}, "class_type": "SaveImage"},
}

# img2img workflow — LoadImage + VAEEncode вместо EmptyLatentImage
FLUX_IMG2IMG_WORKFLOW = {
    "1": {"inputs": {"ckpt_name": "flux1-schnell-fp8.safetensors"}, "class_type": "CheckpointLoaderSimple"},
    "2": {"inputs": {"text": "PROMPT_PLACEHOLDER", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
    "3": {"inputs": {"text": "", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
    "4": {"inputs": {"image": "INPUT_IMAGE", "upload": "image"}, "class_type": "LoadImage"},
    "5": {"inputs": {"image": ["4", 0], "upscale_method": "lanczos",
                     "width": 1024, "height": 1024, "crop": "disabled"}, "class_type": "ImageScale"},
    "6": {"inputs": {"pixels": ["5", 0], "vae": ["1", 2]}, "class_type": "VAEEncode"},
    "7": {"inputs": {
        "seed": 0, "steps": 4, "cfg": 1.0, "sampler_name": "euler",
        "scheduler": "simple", "denoise": 0.75,
        "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
        "latent_image": ["6", 0]
    }, "class_type": "KSampler"},
    "8": {"inputs": {"samples": ["7", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
    "9": {"inputs": {"filename_prefix": "flux_i2i", "images": ["8", 0]}, "class_type": "SaveImage"},
}


class ComfyUIClient:
    """Client for ComfyUI FLUX service."""

    def __init__(self, base_url: str = "http://localhost:8188",
                 ckpt_name: str = "flux1-schnell-fp8.safetensors"):
        self.base_url = base_url.rstrip("/")
        self.ckpt_name = ckpt_name
        self._multiview_cache: dict = {}  # image_path -> list of (b64, name)

    async def check_health(self, timeout_seconds: float = 2.5) -> bool:
        """Quick health check for ComfyUI service availability."""
        timeout = aiohttp.ClientTimeout(
            total=timeout_seconds,
            connect=min(timeout_seconds, 1.5),
            sock_connect=min(timeout_seconds, 1.5),
            sock_read=timeout_seconds,
        )
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/system_stats") as resp:
                    return resp.status == 200
        except Exception as exc:
            logger.warning(f"ComfyUI health check failed: {exc}")
            return False

    async def _run_workflow(self, workflow: dict, session: aiohttp.ClientSession) -> bytes:
        """Queue workflow and poll until done, return raw image bytes."""
        client_id = str(uuid.uuid4())
        try:
            async with session.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow, "client_id": client_id},
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"ComfyUI queue error: {resp.status} {await resp.text()}")
                prompt_id = (await resp.json())["prompt_id"]
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise RuntimeError(
                "ComfyUI unavailable while queueing prompt. "
                "Service may be restarting or out of resources."
            ) from exc

        logger.info(f"Queued prompt {prompt_id}")

        consecutive_poll_errors = 0
        for _ in range(900):  # max 15 min (model download + inference)
            await asyncio.sleep(2)
            try:
                async with session.get(f"{self.base_url}/history/{prompt_id}") as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"ComfyUI history error: {resp.status}")
                    history = await resp.json()
                consecutive_poll_errors = 0
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as exc:
                consecutive_poll_errors += 1
                logger.warning(
                    f"ComfyUI history poll failed ({consecutive_poll_errors}/3): {exc}"
                )
                if consecutive_poll_errors >= 3:
                    raise RuntimeError(
                        "ComfyUI became unavailable during generation. "
                        "Try again after the service recovers."
                    ) from exc
                continue

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                break
        else:
            raise TimeoutError("ComfyUI generation timed out")

        for node_output in outputs.values():
            images = node_output.get("images", [])
            if images:
                filename = images[0]["filename"]
                subfolder = images[0].get("subfolder", "")
                params = {"filename": filename, "type": "output"}
                if subfolder:
                    params["subfolder"] = subfolder
                try:
                    async with session.get(f"{self.base_url}/view", params=params) as resp:
                        if resp.status != 200:
                            raise RuntimeError(f"ComfyUI view error: {resp.status}")
                        return await resp.read()
                except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as exc:
                    raise RuntimeError("Failed to fetch generated image from ComfyUI") from exc

        raise RuntimeError("No image in ComfyUI output")

    async def generate(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        num_inference_steps: int = 4,
        size: str = "1024x1024",
        seed: Optional[int] = None,
    ) -> Dict:
        w, h = map(int, size.split("x"))
        workflow = json.loads(json.dumps(FLUX_TXT2IMG_WORKFLOW))
        workflow["1"]["inputs"]["ckpt_name"] = self.ckpt_name
        workflow["2"]["inputs"]["text"] = prompt
        # dev нужно больше шагов для качества
        if num_inference_steps == 4 and "dev" in self.ckpt_name:
            num_inference_steps = 20
        workflow["5"]["inputs"]["steps"] = num_inference_steps
        workflow["4"]["inputs"]["width"] = w
        workflow["4"]["inputs"]["height"] = h
        workflow["5"]["inputs"]["seed"] = seed if seed is not None else random.randint(0, 2**32 - 1)

        timeout = aiohttp.ClientTimeout(total=60, connect=8, sock_connect=8, sock_read=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            image_bytes = await self._run_workflow(workflow, session)

        image_b64 = base64.b64encode(image_bytes).decode()
        logger.info("txt2img complete")
        return {
            "image_path": f"flux_{uuid.uuid4().hex[:8]}.png",
            "image_base64": image_b64,
            "provider": "flux-schnell-comfyui",
            "metadata": {"model": "FLUX.1-schnell", "steps": num_inference_steps, "size": size},
        }

    async def img2img(
        self,
        image_path: str,
        prompt: str,
        denoise: float = 0.75,
        num_inference_steps: int = 12,
        seed: Optional[int] = None,
    ) -> Dict:
        """Image-to-image via FLUX: upload input image, encode to latent, denoise."""
        timeout = aiohttp.ClientTimeout(total=60, connect=8, sock_connect=8, sock_read=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Upload image to ComfyUI /upload/image
            with open(image_path, "rb") as f:
                image_bytes_in = f.read()
            upload_name = f"i2i_{uuid.uuid4().hex[:8]}.png"
            form = aiohttp.FormData()
            form.add_field("image", image_bytes_in, filename=upload_name, content_type="image/png")
            async with session.post(f"{self.base_url}/upload/image", data=form) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Upload failed: {resp.status} {await resp.text()}")
                uploaded = await resp.json(content_type=None)
                remote_name = uploaded.get("name", upload_name)
            logger.info(f"Uploaded image as {remote_name}")

            workflow = json.loads(json.dumps(FLUX_IMG2IMG_WORKFLOW))
            workflow["1"]["inputs"]["ckpt_name"] = self.ckpt_name
            workflow["2"]["inputs"]["text"] = prompt
            workflow["4"]["inputs"]["image"] = remote_name
            workflow["7"]["inputs"]["denoise"] = denoise
            if num_inference_steps == 4 and "dev" in self.ckpt_name:
                num_inference_steps = 20
            workflow["7"]["inputs"]["steps"] = num_inference_steps
            workflow["7"]["inputs"]["seed"] = seed if seed is not None else random.randint(0, 2**32 - 1)

            image_bytes_out = await self._run_workflow(workflow, session)

        image_b64 = base64.b64encode(image_bytes_out).decode()
        logger.info("img2img complete")
        return {
            "image_path": f"flux_i2i_{uuid.uuid4().hex[:8]}.png",
            "image_base64": image_b64,
            "provider": "flux-schnell-comfyui-img2img",
            "metadata": {"model": "FLUX.1-schnell", "denoise": denoise, "steps": num_inference_steps},
        }

    async def generate_multiview(
        self,
        image_path: str,
        inference_steps: int = 75,
    ) -> list:
        """
        Generate 6 multi-view images using Zero123Plus.
        Returns list of (image_bytes, view_name) tuples.
        Zero123Plus outputs a 640x960 grid (2 cols x 3 rows of 320x320).
        Views: row0=(az30,az90,az150), row1=(az210,az270,az330)
        """
        from PIL import Image
        import io

        if image_path in self._multiview_cache:
            logger.info("Returning cached Zero123Plus views")
            return self._multiview_cache[image_path]

        timeout = aiohttp.ClientTimeout(total=60, connect=8, sock_connect=8, sock_read=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Upload image — convert to RGB so ComfyUI LoadImage accepts it (rejects RGBA)
            img_pil = Image.open(image_path).convert("RGBA")
            # Composite onto white background to flatten alpha
            bg = Image.new("RGB", img_pil.size, (255, 255, 255))
            bg.paste(img_pil, mask=img_pil.split()[3])
            buf_up = io.BytesIO()
            bg.save(buf_up, format="PNG")
            img_bytes = buf_up.getvalue()
            upload_name = f"mv_{uuid.uuid4().hex[:8]}.png"
            form = aiohttp.FormData()
            form.add_field("image", img_bytes, filename=upload_name, content_type="image/png")
            async with session.post(f"{self.base_url}/upload/image", data=form) as resp:
                raw = await resp.text()
                logger.debug(f"Multiview upload response ({resp.status}): {raw[:200]}")
                try:
                    uploaded = json.loads(raw)
                    remote_name = uploaded.get("name", upload_name) if isinstance(uploaded, dict) else upload_name
                except Exception:
                    logger.warning(f"Upload response not JSON ({raw[:50]!r}), using: {upload_name}")
                    remote_name = upload_name

            workflow = {
                "1": {"inputs": {"image": remote_name, "upload": "image"}, "class_type": "LoadImage"},
                "2": {"inputs": {
                    "images": ["1", 0],
                    "ckpt_name": "sudo-ai/zero123plus-v1.1",
                    "pipeline_name": "sudo-ai/zero123plus-pipeline",
                    "inference_steps": inference_steps,
                }, "class_type": "Stablezero123"},
                "3": {"inputs": {"filename_prefix": "zero123_grid", "images": ["2", 0]}, "class_type": "SaveImage"},
            }

            grid_bytes = await self._run_workflow(workflow, session)

        # Split 640x960 grid into 6 views of 320x320
        grid = Image.open(io.BytesIO(grid_bytes))
        view_names = ["front-right", "right", "back-right", "back-left", "left", "front-left"]
        views = []
        for i, name in enumerate(view_names):
            col = i % 2
            row = i // 2
            x, y = col * 320, row * 320
            tile = grid.crop((x, y, x + 320, y + 320))
            buf = io.BytesIO()
            tile.save(buf, format="PNG")
            views.append((base64.b64encode(buf.getvalue()).decode(), name))

        self._multiview_cache[image_path] = views
        logger.info(f"Generated {len(views)} views via Zero123Plus")
        return views
