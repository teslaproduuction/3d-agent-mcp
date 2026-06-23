"""
Tripo3D API client for 3D model generation
"""
import aiohttp
import asyncio
from typing import Optional, Dict, Literal, List
from pathlib import Path
import uuid


class Tripo3DClient:
    """Client for Tripo3D API"""

    BASE_URL = "https://api.tripo3d.ai/v2/openapi"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def text_to_3d(
        self,
        prompt: str,
        model_version: str = "v2.0-20240919",
        face_limit: int = 10000,
        texture: bool = True,
        pbr: bool = False
    ) -> Dict:
        """
        Generate 3D model from text description

        Args:
            prompt: Text description of the 3D object
            model_version: Model version to use
            face_limit: Maximum number of faces (10k, 30k, 50k, 100k)
            texture: Whether to generate texture
            pbr: Whether to generate PBR materials

        Returns:
            Dict with task_id and model info
        """
        # Ensure prompt is a string
        if isinstance(prompt, list):
            prompt = ' '.join(str(item) for item in prompt)
        elif not isinstance(prompt, str):
            prompt = str(prompt)

        async with aiohttp.ClientSession() as session:
            # Create task
            create_url = f"{self.BASE_URL}/task"
            payload = {
                "type": "text_to_model",
                "prompt": prompt,
                "model_version": model_version,
                "face_limit": face_limit,
                "texture": texture,
                "pbr": pbr
            }

            async with session.post(
                create_url,
                headers=self.headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Tripo3D API error: {error_text}")

                result = await response.json()
                task_id = result['data']['task_id']

            # Poll until complete
            model_data = await self._wait_for_task(task_id)

            # Debug logging
            from utils.logger import get_logger
            logger = get_logger(__name__)
            logger.debug(f"text_to_3d model_data: {model_data}")
            logger.debug(f"Output keys: {model_data.get('output', {}).keys() if 'output' in model_data else 'No output'}")

            # Download model
            if 'output' not in model_data:
                raise Exception(f"No 'output' in model_data: {model_data}")

            # Try both 'model' and 'pbr_model' keys
            model_url = None
            if 'model' in model_data['output']:
                model_url = model_data['output']['model']
            elif 'pbr_model' in model_data['output']:
                model_url = model_data['output']['pbr_model']
            else:
                raise Exception(f"No 'model' or 'pbr_model' in output. Available keys: {list(model_data['output'].keys())}")

            model_path = await self._download_model(model_url)

            return {
                'task_id': task_id,
                'model_path': str(model_path),
                'thumbnail_url': model_data['output'].get('rendered_image'),
                'metadata': model_data
            }

    async def multiview_to_3d(
        self,
        image_paths: List[str],
        model_version: str = "v2.5-20250123",
        face_limit: int = 10000,
        texture: bool = True,
        texture_quality: str = "standard"
    ) -> Dict:
        """
        Generate 3D model from multiple view images

        Args:
            image_paths: List of image paths [front, back, left, right]
                        At minimum, front view is required
            model_version: Model version to use
            face_limit: Maximum number of faces
            texture: Whether to generate texture
            texture_quality: "standard" | "HD" | "no"

        Returns:
            Dict with task_id and model info
        """
        async with aiohttp.ClientSession() as session:
            # Upload all images and get tokens
            image_tokens = []
            upload_url = f"{self.BASE_URL}/upload"
            upload_headers = {"Authorization": f"Bearer {self.api_key}"}

            for image_path in image_paths:
                with open(image_path, 'rb') as f:
                    image_data = f.read()

                form_data = aiohttp.FormData()
                form_data.add_field('file', image_data, filename=Path(image_path).name)

                async with session.post(
                    upload_url,
                    headers=upload_headers,
                    data=form_data
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Image upload failed for {image_path}: {error_text}")

                    upload_result = await response.json()
                    image_tokens.append(upload_result['data']['image_token'])

            # Create task with multiview
            create_url = f"{self.BASE_URL}/task"

            # Build file list for multiview (front, back, left, right)
            files = []
            view_names = ['front', 'back', 'left', 'right']
            for i, token in enumerate(image_tokens[:4]):  # Max 4 views
                files.append({
                    "type": "png",
                    "file_token": token
                })

            payload = {
                "type": "multiview_to_model",
                "files": files,
                "model_version": model_version,
                "face_limit": face_limit,
                "texture": texture
            }

            async with session.post(
                create_url,
                headers=self.headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Tripo3D multiview API error: {error_text}")

                result = await response.json()
                task_id = result['data']['task_id']

            # Poll until complete
            model_data = await self._wait_for_task(task_id)

            # Debug logging
            from utils.logger import get_logger
            logger = get_logger(__name__)
            logger.debug(f"multiview_to_3d model_data: {model_data}")
            logger.debug(f"Output keys: {model_data.get('output', {}).keys() if 'output' in model_data else 'No output'}")

            # Download model
            if 'output' not in model_data:
                raise Exception(f"No 'output' in model_data: {model_data}")

            # Try both 'model' and 'pbr_model' keys
            model_url = None
            if 'model' in model_data['output']:
                model_url = model_data['output']['model']
            elif 'pbr_model' in model_data['output']:
                model_url = model_data['output']['pbr_model']
            else:
                raise Exception(f"No 'model' or 'pbr_model' in output. Available keys: {list(model_data['output'].keys())}")

            model_path = await self._download_model(model_url)

            return {
                'task_id': task_id,
                'model_path': str(model_path),
                'thumbnail_url': model_data['output'].get('rendered_image'),
                'metadata': model_data
            }

    async def image_to_3d(
        self,
        image_path: str,
        model_version: str = "v2.0-20240919",
        face_limit: int = 10000,
        texture: bool = True
    ) -> Dict:
        """
        Generate 3D model from image

        Args:
            image_path: Path to input image
            model_version: Model version to use
            face_limit: Maximum number of faces
            texture: Whether to generate texture

        Returns:
            Dict with task_id and model info
        """
        async with aiohttp.ClientSession() as session:
            # Upload image first
            upload_url = f"{self.BASE_URL}/upload"

            with open(image_path, 'rb') as f:
                image_data = f.read()

            form_data = aiohttp.FormData()
            form_data.add_field('file', image_data, filename='image.png')

            upload_headers = {"Authorization": f"Bearer {self.api_key}"}

            async with session.post(
                upload_url,
                headers=upload_headers,
                data=form_data
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Image upload failed: {error_text}")

                upload_result = await response.json()
                image_token = upload_result['data']['image_token']

            # Create task
            create_url = f"{self.BASE_URL}/task"
            payload = {
                "type": "image_to_model",
                "file": {"type": "png", "file_token": image_token},
                "model_version": model_version,
                "face_limit": face_limit,
                "texture": texture
            }

            async with session.post(
                create_url,
                headers=self.headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Tripo3D API error: {error_text}")

                result = await response.json()
                task_id = result['data']['task_id']

            # Poll until complete
            model_data = await self._wait_for_task(task_id)

            # Debug logging
            from utils.logger import get_logger
            logger = get_logger(__name__)
            logger.debug(f"image_to_3d model_data: {model_data}")
            logger.debug(f"Output keys: {model_data.get('output', {}).keys() if 'output' in model_data else 'No output'}")

            # Download model
            if 'output' not in model_data:
                raise Exception(f"No 'output' in model_data: {model_data}")

            # Try both 'model' and 'pbr_model' keys
            model_url = None
            if 'model' in model_data['output']:
                model_url = model_data['output']['model']
            elif 'pbr_model' in model_data['output']:
                model_url = model_data['output']['pbr_model']
            else:
                raise Exception(f"No 'model' or 'pbr_model' in output. Available keys: {list(model_data['output'].keys())}")

            model_path = await self._download_model(model_url)

            return {
                'task_id': task_id,
                'model_path': str(model_path),
                'thumbnail_url': model_data['output'].get('rendered_image'),
                'metadata': model_data
            }

    async def _wait_for_task(
        self,
        task_id: str,
        poll_interval: int = 5,
        timeout: int = 600
    ) -> Dict:
        """
        Poll task status until completion

        Args:
            task_id: Task identifier
            poll_interval: Seconds between polls
            timeout: Maximum seconds to wait

        Returns:
            Task result data
        """
        check_url = f"{self.BASE_URL}/task/{task_id}"
        elapsed = 0

        async with aiohttp.ClientSession() as session:
            while elapsed < timeout:
                async with session.get(check_url, headers=self.headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Task check failed: {error_text}")

                    result = await response.json()
                    status = result['data']['status']

                    if status == 'success':
                        return result['data']
                    elif status in ['failed', 'cancelled']:
                        raise Exception(f"Task {task_id} failed with status: {status}")

                    # Still running
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval

        raise TimeoutError(f"Task {task_id} timed out after {timeout}s")

    async def _download_model(self, model_url: str, format: str = "glb") -> Path:
        """
        Download generated model file

        Args:
            model_url: URL to model file
            format: File format (glb, fbx, obj)

        Returns:
            Path to downloaded file
        """
        filename = f"model_{uuid.uuid4().hex[:8]}.{format}"
        filepath = Path("outputs/models") / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        async with aiohttp.ClientSession() as session:
            async with session.get(model_url) as response:
                if response.status != 200:
                    raise Exception(f"Model download failed: {response.status}")

                content = await response.read()
                filepath.write_bytes(content)

        return filepath

    async def get_task_status(self, task_id: str) -> Dict:
        """Get status of a task"""
        check_url = f"{self.BASE_URL}/task/{task_id}"

        async with aiohttp.ClientSession() as session:
            async with session.get(check_url, headers=self.headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Task check failed: {error_text}")

                result = await response.json()
                return result['data']

    def __repr__(self):
        return f"Tripo3DClient(api_key='***{self.api_key[-4:]}')"
