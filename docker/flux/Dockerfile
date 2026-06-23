FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    diffusers>=0.30.0 \
    transformers>=4.44.0 \
    accelerate>=0.33.0 \
    sentencepiece \
    protobuf \
    fastapi \
    uvicorn[standard] \
    pillow \
    hf-xet \
    huggingface_hub[hf_xet]

WORKDIR /app
COPY server.py .

RUN mkdir -p /app/outputs

EXPOSE 8001

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
