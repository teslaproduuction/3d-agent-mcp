# Docker Setup Guide for 3D Agent MCP

This guide explains how to run the complete 3D Agent MCP system with Docker, including the main application (powered by UV), Trellis3D, Qwen-Image-Edit, and Ollama.

## What's New: UV Package Manager 🚀

The main application now uses **UV** - a blazing-fast Python package manager written in Rust. This provides:

- **10-100x faster** dependency installation
- **Reproducible builds** with lock files
- **5-10 second** Docker build times (vs 2-3 minutes with pip)
- Automatic Python version management

See [UV_MIGRATION_GUIDE.md](UV_MIGRATION_GUIDE.md) for more details.

## Prerequisites

- Docker installed ([Install Docker](https://docs.docker.com/get-docker/))
- Docker Compose installed ([Install Docker Compose](https://docs.docker.com/compose/install/))
- NVIDIA GPU with CUDA support
- NVIDIA Container Toolkit ([Install Guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html))

## Services Overview

### 1. Main Application (3D Agent MCP) ⭐ NEW
- **Purpose**: Main Gradio web interface for 3D model generation
- **Port**: 80 (via Nginx reverse proxy), 7860 (internal app port)
- **Technology**: Python 3.10 + UV package manager
- **GPU**: Not required (uses cloud APIs by default)
- **Features**: Multi-agent orchestration, image/3D generation, post-processing

### 2. Qwen-Image-Edit (Local Image Generation) ⭐ NEW
- **Purpose**: Local AI image generation and editing
- **Port**: 8001
- **Model**: 20B parameter MMDiT model
- **GPU**: Required (8GB+ VRAM)
- **Features**: Text-to-image, image editing, reference-guided generation

### 3. Trellis3D
- **Purpose**: High-quality local 3D model generation
- **Port**: 8000
- **Source**: https://github.com/UNES97/trellis-3d-docker
- **GPU**: Required (CUDA)

### 4. Ollama
- **Purpose**: Local LLM inference for agents
- **Port**: 11434
- **Documentation**: https://docs.ollama.com/docker
- **GPU**: Recommended (can run on CPU)

### 5. Ollama WebUI (Optional)
- **Purpose**: Web interface for managing Ollama models
- **Port**: 3001
- **Features**: Chat interface, model management

## Quick Start

### 1. Set Up Environment Variables

Create a `.env` file in the project root with your API keys:

```bash
# Required for cloud-based generation (OpenAI, Anthropic, etc.)
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
REPLICATE_API_TOKEN=your_replicate_token_here
TRIPO_API_KEY=your_tripo_api_key_here

# Optional: Other API keys
MESHY_API_KEY=your_meshy_api_key_here
```

### 2. Build and Start All Services

```bash
# Build the main application and start all services
docker-compose up -d --build

# Check status
docker-compose ps

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f app
```

**Expected output:**
- Main app running at http://localhost
- Qwen-Image-Edit at http://localhost:8001
- Trellis3D at http://localhost:8000
- Ollama at http://localhost:11434
- Ollama WebUI at http://localhost:3001

### 3. Configure Ollama Models

After starting Ollama, pull the models you want to use:

```bash
# Pull Llama 3.1 (8B)
docker exec -it 3d-agent-ollama ollama pull llama3.1

# Pull Mistral (7B)
docker exec -it 3d-agent-ollama ollama pull mistral

# Pull Llama 3.1 (70B) - requires more VRAM
docker exec -it 3d-agent-ollama ollama pull llama3.1:70b

# List installed models
docker exec -it 3d-agent-ollama ollama list
```

### 3. Update Configuration

Update `config.yaml` to use Docker services:

```yaml
# Enable local 3D models
default_settings:
  local_3d_models:
    enabled: true
    available_models:
      - name: "trellis3d"
        display_name: "Trellis3D (Docker)"
        mode: "docker"
        docker_url: "http://localhost:8000"

# Enable Ollama for LLM
llm:
  local:
    enabled: true
    ollama_base_url: "http://localhost:11434/v1"
    ollama_models: ["llama3.1", "mistral"]
```

### 4. Test Services

**Access Main Application:**
Open http://localhost in your browser - you should see the Gradio interface

**Test Qwen-Image-Edit:**
```bash
curl http://localhost:8001/health
```

**Test Trellis3D:**
```bash
curl http://localhost:8000/health
```

**Test Ollama:**
```bash
curl http://localhost:11434/api/tags
```

**Access Ollama WebUI:**
Open http://localhost:3001 in your browser

## Service Management

### Start Services
```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d trellis3d
docker-compose up -d ollama
```

### Stop Services
```bash
# Stop all services
docker-compose down

# Stop but keep volumes (data preserved)
docker-compose stop
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f trellis3d
docker-compose logs -f ollama
```

### Restart Services
```bash
# Restart all
docker-compose restart

# Restart specific
docker-compose restart trellis3d
```

## Docker Build Performance with UV

The main application uses UV for dependency management, which provides **dramatic speedups**:

### Build Time Comparison

| Method | First Build | Rebuild (cache) | Dependency Install |
|--------|-------------|-----------------|-------------------|
| **pip** | ~5-7 minutes | ~2-3 minutes | ~2-3 minutes |
| **UV** | **~30-60 seconds** | **~10-15 seconds** | **~5-10 seconds** |

**Speed improvement: 5-10x faster!** ⚡

### Production vs Development Mode

**Development Mode** (default in docker-compose.yml):
```yaml
volumes:
  - ./agents:/app/agents      # Mount source code
  - ./api_clients:/app/api_clients
  - ./ui:/app/ui
  - ./utils:/app/utils
  - ./outputs:/app/outputs    # Mount outputs
```

**Production Mode** (for deployment):
Remove volume mounts for source code, keep only outputs:
```yaml
volumes:
  - ./outputs:/app/outputs    # Only outputs
  - ./.env:/app/.env:ro       # API keys
```

## Deployment Options

### Option 1: All Services (Full Local Stack)

Run everything locally including image/3D generation:
```bash
docker-compose up -d
```

**Pros:**
- Complete privacy (no cloud API calls)
- No API costs
- Offline capability

**Cons:**
- Requires powerful GPU (24GB+ VRAM recommended)
- Slower generation than cloud APIs

### Option 2: Hybrid (Main App + Cloud APIs)

Run only the main app, use cloud APIs for generation:
```bash
# Start only the main app
docker-compose up -d app

# Or build and run separately
docker build -t 3d-agent-mcp .
docker run -p 7860:7860 --env-file .env 3d-agent-mcp
```

**Pros:**
- Minimal resource requirements
- Faster generation (cloud GPUs)
- Easy to scale

**Cons:**
- Requires API keys and internet
- API costs

### Option 3: Selective Services

Start only what you need:
```bash
# Main app + Ollama (local LLM, cloud image/3D)
docker-compose up -d app ollama

# Main app + Qwen (local images, cloud 3D)
docker-compose up -d app qwen-image-edit

# Main app + Trellis3D (local 3D, cloud images)
docker-compose up -d app trellis3d
```

## Resource Requirements

### Main Application
- **CPU**: 2+ cores
- **RAM**: 4GB+ recommended
- **Disk**: ~2GB for dependencies
- **GPU**: Not required (unless using local models)

### Qwen-Image-Edit
- **GPU Memory**: 8GB+ VRAM (12GB+ recommended)
- **RAM**: 16GB+
- **Disk**: ~20GB for model weights

### Trellis3D
- **GPU Memory**: 8GB+ VRAM recommended
- **RAM**: 16GB+ recommended
- **Disk**: ~10GB for model weights

### Ollama
- **Llama 3.1 (8B)**: 8GB VRAM or 16GB RAM (CPU mode)
- **Llama 3.1 (70B)**: 48GB+ VRAM
- **Mistral (7B)**: 8GB VRAM or 16GB RAM (CPU mode)

## Troubleshooting

### GPU Not Detected

Check NVIDIA Container Toolkit installation:
```bash
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

### Ollama Models Not Downloading

Check internet connection and disk space:
```bash
# Check Ollama logs
docker logs 3d-agent-ollama

# Free up disk space if needed
docker system prune -a
```

### Trellis3D Service Not Starting

Check logs for errors:
```bash
docker logs 3d-agent-trellis3d

# Verify GPU availability
docker exec -it 3d-agent-trellis3d nvidia-smi
```

### Port Already in Use

Change ports in `docker-compose.yml`:
```yaml
services:
  trellis3d:
    ports:
      - "8001:8000"  # Changed from 8000 to 8001
```

Then update `config.yaml` accordingly.

### Main App Build Fails

**Check UV installation:**
```bash
docker run --rm ghcr.io/astral-sh/uv:latest uv --version
```

**Force rebuild without cache:**
```bash
docker-compose build --no-cache app
```

**Check if uv.lock exists:**
```bash
# Generate lock file if missing
uv lock
```

### Main App Won't Start

**Check logs for errors:**
```bash
docker logs 3d-agent-mcp
```

**Common issues:**
- Missing `.env` file → Create it with API keys
- Port 80 already in use → Change Nginx port mapping in docker-compose.yml
- Missing dependencies → Rebuild with `docker-compose build app`

### Dependency Issues

If you update dependencies:
```bash
# Update pyproject.toml, then regenerate lock file
uv lock --upgrade

# Rebuild container
docker-compose up -d --build app
```

## Using Trellis3D in the Application

Once Trellis3D is running, select it in the UI:

1. Open the web interface (http://localhost)
2. Go to Settings → 3D Generation
3. Select "Локальная модель" mode
4. Choose "Trellis3D (Docker)" from the dropdown
5. Generate your 3D models!

## Using Ollama for Agents

To use Ollama instead of OpenAI/Anthropic:

1. Update `config.yaml`:
```yaml
llm:
  default_provider: "ollama"
  local:
    enabled: true
    ollama_base_url: "http://localhost:11434/v1"
```

2. Run the application with `--use-local-llm` flag:
```bash
python main.py --use-local-llm
```

## Cleaning Up

Remove all containers and volumes:
```bash
# Stop and remove containers
docker-compose down

# Remove volumes (WARNING: deletes all data)
docker-compose down -v

# Remove images
docker rmi unes97/trellis-3d:latest ollama/ollama:latest
```

## Additional Resources

- **Trellis3D Docker**: https://github.com/UNES97/trellis-3d-docker
- **Ollama Documentation**: https://docs.ollama.com/
- **Ollama Docker Guide**: https://docs.ollama.com/docker
- **NVIDIA Container Toolkit**: https://github.com/NVIDIA/nvidia-container-toolkit

## Support

For issues with:
- **Trellis3D**: Open an issue at https://github.com/UNES97/trellis-3d-docker/issues
- **Ollama**: Check https://github.com/ollama/ollama/issues
- **This Integration**: Open an issue in this repository
