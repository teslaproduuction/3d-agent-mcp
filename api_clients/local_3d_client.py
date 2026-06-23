"""
Local 3D model client for running models locally (TripoSR, Shap-E, Instant3D)
"""
from pathlib import Path
from typing import Dict, Optional, List, Union
import logging
import asyncio
from datetime import datetime

from PIL import Image
import torch
import numpy as np
import aiohttp
import io
import base64

from utils.logger import get_logger
from utils.config import Config

logger = get_logger(__name__)


class Local3DClient:
    """
    Client for local 3D generation models
    Supports: TripoSR, Shap-E, Instant3D
    """

    def __init__(
        self,
        model_name: str = "triposr",
        device: Optional[str] = None,
        config: Optional[Config] = None
    ):
        """
        Initialize local 3D client

        Args:
            model_name: Name of the model to use (triposr, shap-e, instant3d)
            device: Device to use (cuda, cpu, mps). Auto-detects if None
            config: Configuration object (optional)
        """
        self.model_name = model_name.lower()
        self.config = config

        # Default output directory (also keeps old cached bytecode from crashing)
        self.output_dir = Path("outputs/3d")

        # Check if model is Docker-based
        self.is_docker_model = False
        self.docker_url = None
        self.docker_endpoint = None
        self.is_multiview_model = False

        if config:
            models_config = config.get('default_settings.local_3d_models', {})
            available_models = models_config.get('available_models', [])

            for model in available_models:
                if model.get('name') == model_name and model.get('mode') == 'docker':
                    self.is_docker_model = True
                    self.docker_url = model.get('docker_url', 'http://localhost:8000')
                    self.docker_endpoint = model.get('api_endpoint', '/api/generate')
                    self.is_multiview_model = model.get('multiview', False)
                    logger.info(f"Model {model_name} is Docker-based: {self.docker_url} multiview={self.is_multiview_model}")
                    break

        # Auto-detect device if not provided (for non-Docker models)
        if not self.is_docker_model:
            if device is None:
                if torch.cuda.is_available():
                    self.device = "cuda"
                elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                    self.device = "mps"
                else:
                    self.device = "cpu"
            else:
                self.device = device
        else:
            self.device = "docker"

        logger.info(f"Initializing Local3DClient with model: {self.model_name}, device: {self.device}")

        # Load model
        self.model = None
        if not self.is_docker_model:
            self._load_model()
        else:
            self.model = True  # Flag for Docker models

    def _load_model(self):
        """Load the specified model"""
        try:
            if self.model_name == "triposr":
                self._load_triposr()
            elif self.model_name == "shap-e":
                self._load_shape()
            elif self.model_name == "instant3d":
                self._load_instant3d()
            else:
                raise ValueError(f"Unsupported model: {self.model_name}")

            logger.info(f"Model {self.model_name} loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load model {self.model_name}: {e}")
            raise

    def _load_triposr(self):
        """Load TripoSR model"""
        try:
            # Try to import TripoSR
            try:
                from tsr.system import TSR
                from tsr.utils import remove_background, resize_foreground

                self.model = TSR.from_pretrained(
                    "stabilityai/TripoSR",
                    config_name="config.yaml",
                    weight_name="model.ckpt",
                )
                self.model.renderer.set_chunk_size(8192)
                self.model.to(self.device)

                # Store utility functions
                self.triposr_utils = {
                    'remove_background': remove_background,
                    'resize_foreground': resize_foreground
                }

                logger.info("TripoSR loaded successfully")

            except ImportError:
                logger.warning("TripoSR not installed. Install with: pip install triposr")
                logger.info("Using stub implementation")
                self.model = None

        except Exception as e:
            logger.error(f"Failed to load TripoSR: {e}")
            raise

    def _load_shape(self):
        """Load Shap-E model"""
        try:
            # Try to import Shap-E
            try:
                from shap_e.diffusion.sample import sample_latents
                from shap_e.diffusion.gaussian_diffusion import diffusion_from_config
                from shap_e.models.download import load_model, load_config
                from shap_e.util.notebooks import decode_latent_mesh

                # Load models
                self.shap_e_xm = load_model('transmitter', device=self.device)
                self.shap_e_model = load_model('image300M', device=self.device)
                self.shap_e_diffusion = diffusion_from_config(load_config('diffusion'))

                # Store utility functions
                self.shap_e_utils = {
                    'sample_latents': sample_latents,
                    'decode_latent_mesh': decode_latent_mesh
                }

                self.model = True  # Flag that model is loaded
                logger.info("Shap-E loaded successfully")

            except ImportError:
                logger.warning("Shap-E not installed. Install with: pip install shap-e")
                logger.info("Using stub implementation")
                self.model = None

        except Exception as e:
            logger.error(f"Failed to load Shap-E: {e}")
            raise

    def _load_instant3d(self):
        """Load Instant3D model"""
        logger.warning("Instant3D not yet implemented. Using stub.")
        self.model = None

    async def generate_from_image(
        self,
        image_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
        **kwargs
    ) -> Dict:
        """
        Generate 3D model from a single image

        Args:
            image_path: Path to input image
            output_dir: Directory to save output (default: outputs/models)
            **kwargs: Additional model-specific parameters

        Returns:
            Dict with keys:
                - model_path: Path to generated GLB/OBJ file
                - metadata: Generation metadata
                - error: Error message if failed
        """
        image_path = Path(image_path)

        if not image_path.exists():
            return {'error': f"Image not found: {image_path}"}

        if output_dir is None:
            output_dir = Path("outputs/models")
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Generating 3D from image: {image_path}")

        try:
            # Load image; composite transparent background onto white for Hunyuan3D
            image = Image.open(image_path)
            if image.mode == 'RGBA':
                white_bg = Image.new('RGB', image.size, (255, 255, 255))
                white_bg.paste(image, mask=image.split()[3])
                image = white_bg
            else:
                image = image.convert('RGB')

            # Generate based on model type
            if self.is_docker_model:
                # Use Docker API
                result = await self._generate_docker(image, output_dir, **kwargs)
            elif self.model_name == "triposr":
                result = await self._generate_triposr(image, output_dir, **kwargs)
            elif self.model_name == "shap-e":
                result = await self._generate_shape(image, output_dir, **kwargs)
            elif self.model_name == "instant3d":
                result = await self._generate_instant3d(image, output_dir, **kwargs)
            else:
                return {'error': f"Unsupported model: {self.model_name}"}

            return result

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {'error': str(e)}

    async def _generate_docker(
        self,
        image: Image.Image,
        output_dir: Path,
        **kwargs
    ) -> Dict:
        """
        Generate using Docker-based model (e.g., Trellis3D)

        Args:
            image: Input PIL Image
            output_dir: Output directory
            **kwargs: Additional parameters

        Returns:
            Dict with model_path and metadata
        """
        if not self.docker_url:
            return {'error': "Docker URL not configured"}

        try:
            # Convert image to base64
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()
            img_base64 = base64.b64encode(img_byte_arr).decode('utf-8')

            # Prepare API request
            url = f"{self.docker_url}{self.docker_endpoint}"

            payload = {
                'image': img_base64,
                'format': 'glb',
                # High-quality defaults for Hunyuan3D-2 full model:
                # octree_resolution 256 = ~8x more triangles vs default 128
                # num_inference_steps 50 = much better geometry vs default 5
                'octree_resolution': kwargs.pop('octree_resolution', 256),
                'num_inference_steps': kwargs.pop('num_inference_steps', 50),
                **kwargs
            }

            logger.info(f"Sending request to Docker API: {url} octree={payload['octree_resolution']} steps={payload['num_inference_steps']}")

            async with aiohttp.ClientSession() as session:
                # Use async /send + /status polling (non-blocking)
                send_url = f"{self.docker_url}/send"
                async with session.post(send_url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        return {'error': f"API returned status {resp.status}: {error_text}"}
                    send_result = await resp.json()
                    uid = send_result.get('uid')

                if not uid:
                    return {'error': "No uid returned from /send"}

                logger.info(f"Generation started, uid={uid}")

                # Poll /status/{uid}
                status_url = f"{self.docker_url}/status/{uid}"
                for _ in range(600):  # max 10 min
                    await asyncio.sleep(2)
                    async with session.get(status_url) as resp:
                        status_result = await resp.json()
                    if status_result.get('status') == 'completed':
                        model_data = base64.b64decode(status_result['model_base64'])
                        break
                    logger.debug(f"Hunyuan3D status: {status_result.get('status')}")
                else:
                    return {'error': "Hunyuan3D generation timed out"}

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = output_dir / f"{self.model_name}_{timestamp}.glb"
                with open(output_path, 'wb') as f:
                    f.write(model_data)

                logger.info(f"Docker generation complete: {output_path}")
                return {
                    'model_path': str(output_path),
                    'metadata': {
                        'model': self.model_name,
                        'device': 'docker',
                        'docker_url': self.docker_url,
                        'timestamp': timestamp,
                    }
                }

        except asyncio.TimeoutError:
            logger.error("Docker API request timed out")
            return {'error': "Request timed out (>300s). Model generation may take longer."}
        except aiohttp.ClientError as e:
            logger.error(f"Docker API connection error: {e}")
            return {'error': f"Failed to connect to Docker service: {str(e)}. Is the container running?"}
        except Exception as e:
            logger.error(f"Docker generation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {'error': str(e)}

    async def _generate_triposr(
        self,
        image: Image.Image,
        output_dir: Path,
        **kwargs
    ) -> Dict:
        """Generate using TripoSR"""
        if self.model is None:
            return {'error': "TripoSR model not loaded"}

        try:
            # Preprocess image
            from tsr.utils import remove_background, resize_foreground

            # Remove background and resize
            image = remove_background(image, rembg_session=None)
            image = resize_foreground(image, 0.85)
            image = np.array(image).astype(np.float32) / 255.0
            image = image[:, :, :3] * image[:, :, 3:4] + (1 - image[:, :, 3:4]) * 0.5
            image = Image.fromarray((image * 255.0).astype(np.uint8))

            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            mesh = await loop.run_in_executor(
                None,
                lambda: self.model.run_image(
                    image,
                    bake_resolution=1024,
                    estimate_illumination=True
                )
            )

            # Save mesh
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"triposr_{timestamp}.glb"

            mesh.export(str(output_path))

            logger.info(f"TripoSR generation complete: {output_path}")

            return {
                'model_path': str(output_path),
                'metadata': {
                    'model': 'triposr',
                    'device': self.device,
                    'timestamp': timestamp
                }
            }

        except Exception as e:
            logger.error(f"TripoSR generation failed: {e}")
            return {'error': str(e)}

    async def _generate_shape(
        self,
        image: Image.Image,
        output_dir: Path,
        guidance_scale: float = 15.0,
        **kwargs
    ) -> Dict:
        """Generate using Shap-E"""
        if self.model is None:
            return {'error': "Shap-E model not loaded"}

        try:
            # Resize image to 256x256
            image = image.resize((256, 256), Image.LANCZOS)

            # Convert to batch
            batch_size = 1
            image_tensor = torch.from_numpy(np.array(image)).permute(2, 0, 1).unsqueeze(0).to(self.device) / 255.0

            # Run in thread pool
            loop = asyncio.get_event_loop()

            def generate():
                # Sample latents
                latents = self.shap_e_utils['sample_latents'](
                    batch_size=batch_size,
                    model=self.shap_e_model,
                    diffusion=self.shap_e_diffusion,
                    guidance_scale=guidance_scale,
                    model_kwargs=dict(images=[image_tensor] * batch_size),
                    progress=True,
                    clip_denoised=True,
                    use_fp16=True,
                    use_karras=True,
                    karras_steps=64,
                    sigma_min=1e-3,
                    sigma_max=160,
                    s_churn=0,
                )

                # Decode to mesh
                mesh = self.shap_e_utils['decode_latent_mesh'](
                    self.shap_e_xm,
                    latents[0]
                ).tri_mesh()

                return mesh

            mesh = await loop.run_in_executor(None, generate)

            # Save mesh
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"shap_e_{timestamp}.ply"

            with open(output_path, 'wb') as f:
                mesh.write_ply(f)

            logger.info(f"Shap-E generation complete: {output_path}")

            return {
                'model_path': str(output_path),
                'metadata': {
                    'model': 'shap-e',
                    'device': self.device,
                    'guidance_scale': guidance_scale,
                    'timestamp': timestamp
                }
            }

        except Exception as e:
            logger.error(f"Shap-E generation failed: {e}")
            return {'error': str(e)}

    async def _generate_instant3d(
        self,
        image: Image.Image,
        output_dir: Path,
        **kwargs
    ) -> Dict:
        """Generate using Instant3D (stub)"""
        return {'error': "Instant3D not yet implemented"}

    async def generate_from_multiview(
        self,
        image_paths: List[Union[str, Path]],
        output_dir: Optional[Union[str, Path]] = None,
        **kwargs
    ) -> Dict:
        """
        Generate 3D model from multiple views.
        hunyuan3d-mv: sends dict {front/left/back/right} for true multiview.
        hunyuan3d (standard): uses front view only.
        """
        if not image_paths:
            return {'error': "No images provided"}

        if self.is_multiview_model and self.docker_url and len(image_paths) > 1:
            logger.info(f"Multiview: sending {len(image_paths)} views to {self.model_name} (mv model)")
            output_dir = Path(output_dir) if output_dir else Path("outputs/3d")
            output_dir.mkdir(parents=True, exist_ok=True)
            return await self._generate_docker_multiview(image_paths, output_dir, **kwargs)

        logger.info(f"Multiview: using front view (image 0 of {len(image_paths)}) for {self.model_name}")
        return await self.generate_from_image(image_paths[0], output_dir, **kwargs)

    async def _generate_docker_multiview(
        self,
        image_paths: List[Union[str, Path]],
        output_dir: Path,
        **kwargs
    ) -> Dict:
        """Send views as named dict {front/left/back/right} to Hunyuan3D-2mv API."""
        if not self.docker_url:
            return {'error': "Docker URL not configured"}

        # Zero123Plus outputs 6 views in a 2x3 grid, already split:
        # index 0 = original front, 1..6 = az30,az90,az150,az210,az270,az330
        # Map to Hunyuan3D-2mv expected keys: front, left, back, right
        view_keys = ["front", "left", "back", "right"]
        try:
            images_dict = {}
            for i, key in enumerate(view_keys):
                if i < len(image_paths):
                    buf = io.BytesIO()
                    # Convert to RGBA — mv model expects RGBA
                    Image.open(image_paths[i]).convert("RGBA").save(buf, format='PNG')
                    images_dict[key] = base64.b64encode(buf.getvalue()).decode('utf-8')

            payload = {
                'images': images_dict,   # dict with front/left/back/right keys
                'format': 'glb',
                'octree_resolution': kwargs.pop('octree_resolution', 256),
                'num_inference_steps': kwargs.pop('num_inference_steps', 50),
                **kwargs
            }

            logger.info(f"Sending views {list(images_dict.keys())} to {self.docker_url}/send octree={payload['octree_resolution']} steps={payload['num_inference_steps']}")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.docker_url}/send",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        return {'error': f"API returned {resp.status}: {await resp.text()}"}
                    uid = (await resp.json()).get('uid')

                if not uid:
                    return {'error': "No uid from /send"}

                status_url = f"{self.docker_url}/status/{uid}"
                for _ in range(600):
                    await asyncio.sleep(2)
                    async with session.get(status_url) as resp:
                        result = await resp.json()
                    if result.get('status') == 'completed':
                        model_data = base64.b64decode(result['model_base64'])
                        break
                    logger.debug(f"Hunyuan3D multiview status: {result.get('status')}")
                else:
                    return {'error': "Hunyuan3D multiview timed out"}

            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"{self.model_name}_mv_{timestamp}.glb"
            with open(output_path, 'wb') as f:
                f.write(model_data)

            logger.info(f"Multiview generation complete: {output_path}")
            return {
                'model_path': str(output_path),
                'metadata': {
                    'model': self.model_name,
                    'views': len(image_paths),
                    'device': 'docker',
                }
            }

        except Exception as e:
            logger.error(f"Multiview generation failed: {e}")
            return {'error': str(e)}

    def is_available(self) -> bool:
        """Check if model is loaded and available"""
        return self.model is not None

    @classmethod
    def get_available_models(cls, config: Optional[Config] = None) -> List[str]:
        """
        Get list of available local models from config

        Args:
            config: Configuration object

        Returns:
            List of model names
        """
        if config is None:
            return ["triposr", "shap-e", "instant3d"]

        models_config = config.get('default_settings.local_3d_models', {})
        if not models_config.get('enabled', False):
            return []

        available = models_config.get('available_models', [])
        return [model['name'] for model in available]
