FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04

RUN apt-get update && apt-get install -y \
    git curl build-essential ninja-build \
    python3 python3-pip python3-dev \
    libgl1 libglib2.0-0 \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Клонируем официальный репозиторий
RUN git clone https://github.com/Tencent/Hunyuan3D-2.git .

# PyTorch cu128 — единственный вариант с поддержкой Blackwell (RTX 5080, sm_120)
RUN pip install --no-cache-dir \
    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
RUN pip install --no-cache-dir -r requirements.txt || true
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] huggingface_hub

# Сборка C++ расширения custom_rasterizer (требует CUDA devel headers + ninja)
RUN cd hy3dgen/texgen/custom_rasterizer && pip install --no-cache-dir . 2>&1 | tail -5 || echo "custom_rasterizer build failed (optional)"
# Сборка differentiable renderer
RUN cd hy3dgen/texgen/differentiable_renderer && pip install --no-cache-dir . 2>&1 | tail -5 || echo "diff_renderer build failed (optional)"

# Патч api_server.py: добавляем --subfolder аргумент и передаём его в ModelWorker
RUN python3 - <<'PYEOF'
import re

with open('/app/api_server.py', 'r') as f:
    code = f.read()

# Добавить --subfolder в argparse (после --tex_model_path)
code = code.replace(
    'parser.add_argument("--tex_model_path", type=str, default=\'tencent/Hunyuan3D-2\')',
    'parser.add_argument("--tex_model_path", type=str, default=\'tencent/Hunyuan3D-2\')\n    parser.add_argument("--subfolder", type=str, default=\'hunyuan3d-dit-v2-mini-turbo\')'
)

# Передать subfolder в ModelWorker
code = code.replace(
    'worker = ModelWorker(model_path=args.model_path, device=args.device, enable_tex=args.enable_tex,\n                         tex_model_path=args.tex_model_path)',
    'worker = ModelWorker(model_path=args.model_path, device=args.device, enable_tex=args.enable_tex,\n                         tex_model_path=args.tex_model_path, subfolder=args.subfolder)'
)

with open('/app/api_server.py', 'w') as f:
    f.write(code)

print("api_server.py patched OK (subfolder)")
PYEOF

# Патч api_server.py: поддержка multiview через 'images' (список base64)
RUN python3 - <<'PYEOF'
with open('/app/api_server.py', 'r') as f:
    lines = f.readlines()

out = []
i = 0
while i < len(lines):
    line = lines[i]
    if "    def generate(self, uid, params):" in line:
        out.append(line)
        i += 1
        while i < len(lines) and "if 'image' in params:" not in lines[i]:
            i += 1
        new_block = """\
        if 'images' in params:
            raw_images = params.pop('images')
            if isinstance(raw_images, dict):
                # Hunyuan3D-2mv: dict with front/left/back/right keys
                images_pil = {k: self.rembg(load_image_from_base64(v)) for k, v in raw_images.items()}
                params['image'] = images_pil
            else:
                # Unexpected list — use first only
                params['image'] = self.rembg(load_image_from_base64(raw_images[0]))
        elif 'image' in params:
            image = load_image_from_base64(params['image'])
            image = self.rembg(image)
            params['image'] = image
        else:
            if 'text' in params:
                text = params['text']
                image = self.pipeline_t2i(text)
                image = self.rembg(image)
                params['image'] = image
            else:
                raise ValueError("No input image or text provided")
"""
        out.append(new_block)
        while i < len(lines) and "if 'mesh' in params:" not in lines[i]:
            i += 1
    else:
        out.append(line)
        i += 1

with open('/app/api_server.py', 'w') as f:
    f.writelines(out)
print("api_server.py patched OK (multiview)")
PYEOF

RUN mkdir -p /app/outputs /app/cache

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8081

ENTRYPOINT ["/entrypoint.sh"]
