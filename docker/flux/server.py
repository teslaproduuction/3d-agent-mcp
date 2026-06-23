"""
FLUX.1-schnell image generation API server
Model loads in background — server starts immediately, healthcheck passes during download.
"""
import io
import base64
import uuid
import os
import logging
import threading
from pathlib import Path
from typing import Optional

import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FLUX.1-schnell API")

OUTPUT_DIR = Path("/app/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

pipe = None
model_loading = False
model_error = None


def load_model_background():
    global pipe, model_loading, model_error
    try:
        from diffusers import FluxPipeline
        from PIL import Image

        hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
        if hf_token:
            from huggingface_hub import login
            login(token=hf_token)
            logger.info("Logged in to HuggingFace")

        logger.info("Loading FLUX.1-schnell model (background)...")
        loaded = FluxPipeline.from_pretrained(
            "black-forest-labs/FLUX.1-schnell",
            torch_dtype=torch.bfloat16,
            token=hf_token,
        )
        loaded.enable_model_cpu_offload()
        pipe = loaded
        logger.info("FLUX.1-schnell ready!")
    except Exception as e:
        model_error = str(e)
        logger.error(f"Model load failed: {e}")
    finally:
        model_loading = False


@app.on_event("startup")
async def startup():
    global model_loading
    model_loading = True
    t = threading.Thread(target=load_model_background, daemon=True)
    t.start()


@app.get("/health")
async def health():
    return {
        "status": "ok" if pipe is not None else ("error" if model_error else "loading"),
        "ready": pipe is not None,
        "model": "FLUX.1-schnell",
        "error": model_error,
    }


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    num_inference_steps: int = 4
    guidance_scale: float = 0.0
    size: str = "1024x1024"
    seed: Optional[int] = None


@app.post("/api/generate")
async def generate(request: GenerateRequest):
    if pipe is None:
        status = "loading" if model_loading else f"error: {model_error}"
        raise HTTPException(status_code=503, detail=f"Model not ready ({status})")

    try:
        from PIL import Image
        w, h = map(int, request.size.split("x"))
        generator = torch.Generator().manual_seed(request.seed) if request.seed else None

        logger.info(f"Generating: '{request.prompt[:80]}' ({w}x{h})")
        result = pipe(
            prompt=request.prompt,
            width=w,
            height=h,
            num_inference_steps=request.num_inference_steps,
            guidance_scale=request.guidance_scale,
            generator=generator,
        )
        image = result.images[0]

        filename = f"{uuid.uuid4().hex}.png"
        filepath = OUTPUT_DIR / filename
        image.save(filepath)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        image_b64 = base64.b64encode(buf.getvalue()).decode()

        logger.info(f"Generated: {filename}")
        return JSONResponse({
            "image_path": str(filepath),
            "image_base64": image_b64,
            "provider": "flux-schnell",
            "metadata": {"model": "FLUX.1-schnell", "steps": request.num_inference_steps, "size": request.size}
        })
    except Exception as e:
        logger.error(f"Generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
