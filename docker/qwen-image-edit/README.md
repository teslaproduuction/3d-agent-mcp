# Qwen-Image-Edit Docker Setup

Docker контейнер для локальной генерации и редактирования изображений с использованием модели Qwen-Image-Edit (20B параметров).

## Особенности

- **Генерация изображений** из текста (text-to-image)
- **Редактирование изображений** (image editing)
- **Multi-view generation** с консистентностью
- **Reference-guided generation** (semantic + appearance control)
- **FP16 оптимизация** для снижения требований к VRAM
- **FastAPI REST API** для интеграции

## Требования

- **GPU**: NVIDIA с 16GB+ VRAM (для FP16)
- **Docker**: с поддержкой NVIDIA Runtime
- **CUDA**: 12.1+
- **Disk**: ~40GB для модели и зависимостей

## Быстрый старт

### Вариант 1: Использовать готовый Docker образ

```bash
# Запуск через docker-compose (рекомендуется)
cd /mnt/d/Проекты/3dAgentMCP
docker-compose up qwen-image-edit
```

### Вариант 2: Собрать свой образ

```bash
cd docker/qwen-image-edit

# Собрать образ
docker build -t qwen-image-edit:latest .

# Запустить контейнер
docker run -d \
  --name qwen-image-edit \
  --gpus all \
  -p 8001:8000 \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e MODEL_NAME=Qwen/Qwen-Image-Edit \
  -e DEVICE=cuda \
  -e USE_FP16=true \
  -v qwen-cache:/root/.cache/huggingface \
  qwen-image-edit:latest
```

## Использование

### Проверка статуса

```bash
curl http://localhost:8001/health
```

Ответ:
```json
{
  "status": "healthy",
  "model_loaded": true
}
```

### Генерация изображения

```bash
curl -X POST http://localhost:8001/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A modern desk organizer, 3D render, product photography, white background",
    "num_inference_steps": 20,
    "guidance_scale": 7.5,
    "size": "1024x1024"
  }'
```

### Редактирование изображения

```bash
# Сначала закодируйте изображение в base64
base64_image=$(base64 -w 0 input.png)

curl -X POST http://localhost:8001/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Same object, but from the back view",
    "base_image": "'$base64_image'",
    "editing_mode": true,
    "strength": 0.6,
    "num_inference_steps": 20,
    "guidance_scale": 7.5,
    "size": "1024x1024"
  }'
```

### Reference-guided Generation (Qwen специфично)

```bash
curl -X POST http://localhost:8001/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Modern smartphone in a minimalist style",
    "base_image": "'$base64_image'",
    "qwen_mode": "reference_guided",
    "semantic_control": 0.7,
    "appearance_control": 0.3,
    "num_inference_steps": 25,
    "guidance_scale": 7.5
  }'
```

## API Параметры

### GenerateRequest

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `prompt` | string | **обязательно** | Текстовое описание желаемого изображения |
| `negative_prompt` | string | null | Что НЕ должно быть на изображении |
| `base_image` | string | null | Base64 кодированное изображение для редактирования |
| `editing_mode` | bool | false | Включить режим редактирования |
| `num_inference_steps` | int | 20 | Количество шагов диффузии (больше = качество, медленнее) |
| `guidance_scale` | float | 7.5 | Насколько следовать промпту (выше = точнее) |
| `size` | string | "1024x1024" | Размер изображения |
| `strength` | float | 0.7 | Сила изменений (0-1, для editing_mode) |
| `semantic_control` | float | null | Семантический контроль (для reference_guided) |
| `appearance_control` | float | null | Контроль внешнего вида (для reference_guided) |
| `qwen_mode` | string | null | Режим Qwen: "reference_guided" или null |

### Response

```json
{
  "image": "<base64_encoded_image>",
  "metadata": {
    "model": "Qwen-Image-Edit",
    "prompt": "...",
    "size": "1024x1024",
    "steps": 20
  }
}
```

## Интеграция с 3dAgentMCP

Сервис автоматически интегрируется при выборе провайдера "local" в UI:

1. Запустите Docker контейнер
2. В Gradio UI выберите:
   - **Генератор изображений**: "local"
3. Система автоматически использует Qwen-Image-Edit

## Производительность

### Время генерации (RTX 4090, FP16)

- **1024x1024, 20 steps**: ~8-12 секунд
- **1024x1024, 25 steps**: ~10-15 секунд
- **Image editing**: ~6-10 секунд

### VRAM использование

- **FP16 (рекомендуется)**: ~14GB
- **FP32**: ~26GB

## Troubleshooting

### Ошибка "CUDA out of memory"

```bash
# Используйте CPU (медленно)
docker run ... -e DEVICE=cpu ...

# Или уменьшите размер изображения
# size: "512x512" вместо "1024x1024"
```

### Модель не загружается

```bash
# Проверьте логи
docker logs qwen-image-edit

# Убедитесь что есть место на диске
df -h

# Очистите кэш Hugging Face
docker exec qwen-image-edit rm -rf /root/.cache/huggingface
```

### Порт занят

```bash
# Измените порт в docker-compose.yml
ports:
  - "8002:8000"  # Вместо 8001
```

## Ссылки

- **Qwen-Image GitHub**: https://github.com/QwenLM/Qwen-Image
- **Hugging Face Model**: https://huggingface.co/Qwen/Qwen-Image-Edit
- **Docker Hub**: https://hub.docker.com/r/dkozlov/qwen-image
- **Документация Diffusers**: https://huggingface.co/docs/diffusers

## Лицензия

Qwen-Image-Edit использует лицензию от Alibaba. Проверьте официальный репозиторий для деталей.
