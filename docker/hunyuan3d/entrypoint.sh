#!/bin/bash
set -e

MODEL_PATH="${MODEL_PATH:-tencent/Hunyuan3D-2mini}"
export HF_HOME="${HF_HOME:-/app/cache}"
export HF_HUB_CACHE="${HF_HOME}/hub"
export HUGGINGFACE_HUB_CACHE="${HF_HOME}/hub"

echo "[hunyuan3d] Pre-downloading model: $MODEL_PATH → $HF_HUB_CACHE"
python3 - <<EOF
from huggingface_hub import snapshot_download
path = snapshot_download(
    repo_id="$MODEL_PATH",
    cache_dir="$HF_HUB_CACHE",
    ignore_patterns=["*.md", "*.txt"],
)
print(f"[hunyuan3d] Model ready: {path}")
EOF

# Offline mode: api_server не будет делать сетевые запросы в HF, только кэш
export HF_HUB_OFFLINE=1

# Выбираем subfolder в зависимости от модели
if echo "$MODEL_PATH" | grep -q "mini"; then
    SUBFOLDER="${SUBFOLDER:-hunyuan3d-dit-v2-mini-turbo}"
elif echo "$MODEL_PATH" | grep -q "\-2mv"; then
    SUBFOLDER="${SUBFOLDER:-hunyuan3d-dit-v2-mv}"
else
    SUBFOLDER="${SUBFOLDER:-hunyuan3d-dit-v2-0-turbo}"
fi
echo "[hunyuan3d] Using subfolder: $SUBFOLDER"

ENABLE_TEX_FLAG=""
if [ "${ENABLE_TEX:-false}" = "true" ]; then
    ENABLE_TEX_FLAG="--enable_tex"
fi

exec python api_server.py \
    --host 0.0.0.0 \
    --port 8081 \
    --model_path "$MODEL_PATH" \
    --subfolder "$SUBFOLDER" \
    $ENABLE_TEX_FLAG \
    "$@"
