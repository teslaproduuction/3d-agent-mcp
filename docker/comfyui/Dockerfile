FROM frefrik/comfyui-flux:cu128

# The base image venv has no pip — bootstrap it first with ensurepip,
# then install packages needed by ComfyUI custom nodes.
RUN /opt/venv/bin/python3 -m ensurepip --upgrade && \
    /opt/venv/bin/python3 -m pip install --no-cache-dir \
        diffusers>=0.30.0 \
        gitpython>=3.1.0 \
        transformers>=4.44.0 \
        accelerate>=0.33.0 \
        omegaconf \
        einops \
        kornia \
        open_clip_torch \
        safetensors \
        sqlalchemy \
        aiosqlite

# Pre-bake custom nodes into the image so they're available on first run
RUN git clone --depth=1 https://github.com/deroberon/StableZero123-comfyui.git \
        /custom_nodes_prebuild/StableZero123-comfyui

# Wrapper: installs pre-baked custom nodes into the volume, then runs original entrypoint
COPY install_custom_nodes.sh /install_custom_nodes.sh
RUN chmod +x /install_custom_nodes.sh
ENTRYPOINT ["/install_custom_nodes.sh"]
