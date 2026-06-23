# ── Stage 1: build / install dependencies ────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 build-essential \
    && rm -rf /var/lib/apt/lists/*

# Project metadata — hatchling needs README.md to build the wheel
COPY pyproject.toml README.md ./

# PyTorch CPU-only: separate RUN so it stays cached even when other deps change.
RUN uv pip install --system --no-cache \
    torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

# Install everything declared in pyproject.toml
RUN uv pip install --system --no-cache .

# ── Stage 2: lean runtime image ───────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bring over the installed site-packages from the build stage
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin            /usr/local/bin

# Application source
COPY agents/         agents/
COPY api_clients/    api_clients/
COPY ui/             ui/
COPY utils/          utils/
COPY mcp_server/     mcp_server/
COPY postprocessing/ postprocessing/
COPY main.py         .
COPY config.yaml     .

# Output and log directories (overridden by volume mounts at runtime)
RUN mkdir -p outputs/models outputs/previews outputs/images outputs/hunyuan3d logs

EXPOSE 7860

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "7860"]
