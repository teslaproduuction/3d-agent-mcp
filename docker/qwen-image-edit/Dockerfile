# Dockerfile for Qwen-Image-Edit local deployment
# Based on official QwenLM/Qwen-Image repository
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create symlink for python
RUN ln -s /usr/bin/python3.10 /usr/bin/python

# Upgrade pip
RUN pip install --upgrade pip

# Install PyTorch with CUDA support
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Install diffusers and transformers
RUN pip install diffusers transformers accelerate safetensors

# Install additional dependencies
RUN pip install \
    fastapi \
    uvicorn[standard] \
    pillow \
    numpy \
    opencv-python \
    aiohttp

# Copy application code
COPY app.py /app/app.py
COPY requirements.txt /app/requirements.txt

# Install app requirements
RUN pip install -r requirements.txt

# Expose port
EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
