#!/bin/bash
# Copies pre-baked custom nodes into the ComfyUI volume (if not already present),
# then hands off to the original base image entrypoint.

CUSTOM_NODES_DIR="/app/ComfyUI/custom_nodes"
PREBUILD_DIR="/custom_nodes_prebuild"

if [ -d "$CUSTOM_NODES_DIR" ] && [ -d "$PREBUILD_DIR" ]; then
    for node_dir in "$PREBUILD_DIR"/*/; do
        node_name=$(basename "$node_dir")
        target="$CUSTOM_NODES_DIR/$node_name"
        if [ ! -d "$target" ]; then
            echo "[custom-nodes] Installing $node_name..."
            cp -r "$node_dir" "$target"
        fi
    done
fi

exec /scripts/entrypoint.sh "$@"
