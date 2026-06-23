"""
Tests for multiview output routing in ImageAPIClient.
"""
import base64
from pathlib import Path

import pytest

from api_clients.image_api_client import ImageAPIClient


@pytest.mark.asyncio
async def test_comfyui_multiview_saves_to_flux_and_previews(tmp_path, monkeypatch):
    """ComfyUI multiview should save primary output to flux and duplicate to previews."""
    monkeypatch.chdir(tmp_path)

    client = ImageAPIClient(
        provider='local',
        local_model_config={
            'mode': 'comfyui',
            'docker_url': 'http://localhost:8188',
        }
    )

    fake_image_b64 = base64.b64encode(b"fake_png_bytes").decode("utf-8")
    fake_views = [
        (fake_image_b64, "front-right"),
        (fake_image_b64, "right"),
        (fake_image_b64, "back-right"),
        (fake_image_b64, "back-left"),
        (fake_image_b64, "left"),
        (fake_image_b64, "front-left"),
    ]

    async def fake_generate_multiview(image_path: str, inference_steps: int = 75):
        _ = image_path
        _ = inference_steps
        return fake_views

    monkeypatch.setattr(client.local_client, 'generate_multiview', fake_generate_multiview)

    result = await client._generate_local_view(
        base_image_path='dummy.png',
        prompt='test object',
        view_description='right side view',
    )

    preview_path = Path(result['image_path'])
    flux_path = Path(result['flux_image_path'])

    assert preview_path.exists()
    assert flux_path.exists()
    assert preview_path.parent == Path('outputs/previews')
    assert flux_path.parent == Path('outputs/flux')
    assert preview_path.read_bytes() == flux_path.read_bytes()
    assert result['provider'] == 'zero123plus'
