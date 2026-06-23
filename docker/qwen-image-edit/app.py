"""
FastAPI server for Qwen-Image-Edit
Provides REST API for image generation and editing
"""
import os
import base64
from io import BytesIO
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from PIL import Image
import torch

app = FastAPI(title="Qwen-Image-Edit Server")

# Global model storage
pipeline = None


class GenerateRequest(BaseModel):
    """Request model for image generation"""
    prompt: str
    negative_prompt: Optional[str] = None
    base_image: Optional[str] = None  # Base64 encoded
    editing_mode: bool = False
    num_inference_steps: int = 20
    guidance_scale: float = 7.5
    size: str = "1024x1024"
    strength: float = 0.7
    semantic_control: Optional[float] = None
    appearance_control: Optional[float] = None
    qwen_mode: Optional[str] = None


@app.on_event("startup")
async def load_model():
    """Load Qwen-Image-Edit model on startup"""
    global pipeline

    try:
        from diffusers import QwenImageEditPipeline

        model_name = os.getenv("MODEL_NAME", "Qwen/Qwen-Image-Edit")
        device = os.getenv("DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
        use_fp16 = os.getenv("USE_FP16", "true").lower() == "true"

        print(f"Loading model: {model_name}")
        print(f"Device: {device}")
        print(f"Use FP16: {use_fp16}")

        # Load pipeline
        pipeline = QwenImageEditPipeline.from_pretrained(
            model_name,
            torch_dtype=torch.float16 if use_fp16 and device == "cuda" else torch.float32
        )

        pipeline = pipeline.to(device)

        # Enable memory efficient attention if available
        if hasattr(pipeline, "enable_xformers_memory_efficient_attention"):
            try:
                pipeline.enable_xformers_memory_efficient_attention()
                print("Enabled xformers memory efficient attention")
            except Exception as e:
                print(f"Could not enable xformers: {e}")

        print("Model loaded successfully!")

    except Exception as e:
        print(f"Error loading model: {e}")
        raise


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "model_loaded": pipeline is not None
    }


@app.post("/api/generate")
async def generate_image(request: GenerateRequest):
    """Generate or edit image based on request"""
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        # Parse size
        width, height = map(int, request.size.split('x'))

        # Decode base image if provided
        base_img = None
        if request.base_image:
            img_data = base64.b64decode(request.base_image)
            base_img = Image.open(BytesIO(img_data)).convert("RGB")

        # Generate image
        if request.editing_mode and base_img:
            # Image editing mode
            output = pipeline(
                prompt=request.prompt,
                image=base_img,
                negative_prompt=request.negative_prompt,
                num_inference_steps=request.num_inference_steps,
                guidance_scale=request.guidance_scale,
                strength=request.strength,
                width=width,
                height=height
            )
        elif request.qwen_mode == "reference_guided" and base_img:
            # Qwen-specific reference-guided mode
            output = pipeline(
                prompt=request.prompt,
                reference_image=base_img,
                semantic_control=request.semantic_control or 0.5,
                appearance_control=request.appearance_control or 0.5,
                num_inference_steps=request.num_inference_steps,
                guidance_scale=request.guidance_scale,
                width=width,
                height=height
            )
        else:
            # Text-to-image mode
            output = pipeline(
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                num_inference_steps=request.num_inference_steps,
                guidance_scale=request.guidance_scale,
                width=width,
                height=height
            )

        # Get generated image
        generated_image = output.images[0]

        # Convert to base64
        buffered = BytesIO()
        generated_image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()

        return {
            "image": img_base64,
            "metadata": {
                "model": "Qwen-Image-Edit",
                "prompt": request.prompt,
                "size": request.size,
                "steps": request.num_inference_steps
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Qwen-Image-Edit Server",
        "version": "1.0.0",
        "model": "Qwen/Qwen-Image-Edit",
        "endpoints": [
            "/api/generate",
            "/health"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
