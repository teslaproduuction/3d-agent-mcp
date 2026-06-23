<div align="center">

# 🖨️ 3D Agent MCP

**Текст → 2D-превью → 3D-модель → STL для печати**

Мультиагентная система генерации 3D-моделей по текстовому описанию с MCP-сервером для интеграции с ИИ-ассистентами.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-22c55e)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-Compatible-5A4FCF?logo=anthropic&logoColor=white)](https://modelcontextprotocol.io)
[![Gradio](https://img.shields.io/badge/UI-Gradio-FF7C00?logo=gradio)](https://gradio.app)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![GHCR](https://img.shields.io/badge/ghcr.io-image-0D1117?logo=github)](https://github.com/teslaproduuction/3d-agent-mcp/pkgs/container/3d-agent-mcp)

🇬🇧 [English](README.md) | 🇷🇺 Русский

<img src="docs/images/v2_text_to_3d_pipeline.png" alt="Пайплайн" width="90%"/>

</div>

---

## Демо

<video src="https://github.com/teslaproduuction/3d-agent-mcp/raw/main/docs/demo.mp4" controls width="100%"></video>

### Примеры генерации

<table>
  <tr>
    <td><img src="docs/PR/data/images/preview_preview_022218a9.png" width="200"/></td>
    <td><img src="docs/PR/data/images/preview_preview_02a7f736.png" width="200"/></td>
    <td><img src="docs/PR/data/images/preview_preview_037a6c8e.png" width="200"/></td>
    <td><img src="docs/PR/data/images/preview_preview_06079652.png" width="200"/></td>
  </tr>
  <tr>
    <td><img src="docs/PR/data/images/preview_preview_066fe8d4.png" width="200"/></td>
    <td><img src="docs/PR/data/images/preview_preview_08134311.png" width="200"/></td>
    <td><img src="docs/PR/data/images/mv_back-right_0a51fab9.png" width="200"/></td>
    <td><img src="docs/PR/data/images/mv_left.png" width="200"/></td>
  </tr>
</table>

*2D-превью генерируется перед 3D — быстрее итерации, меньше трат на API*

### Мультивью-генерация

<table>
  <tr>
    <td><img src="docs/PR/data/images/preview_zero123_right_bf464842.png" width="150"/></td>
    <td><img src="docs/PR/data/images/preview_zero123_right_bf93635c.png" width="150"/></td>
    <td><img src="docs/PR/data/images/preview_zero123_right_c023b3c2.png" width="150"/></td>
    <td><img src="docs/PR/data/images/preview_zero123_right_c46b046f.png" width="150"/></td>
    <td><img src="docs/PR/data/images/preview_zero123_right_d243190d.png" width="150"/></td>
  </tr>
</table>

*Несколько ракурсов → лучшее качество 3D-геометрии через Hunyuan3D-2mv*

---

## Архитектура

### Контекст системы (C4 Level 1)

<img src="docs/images/c4_l1_context.png" alt="C4 Контекст" width="80%"/>

### Контейнеры (C4 Level 2)

<img src="docs/images/c4_l2_containers.png" alt="C4 Контейнеры" width="80%"/>

### Пайплайн агентов

```
Запрос пользователя
    │
    ▼
┌─────────────────────┐
│    Planner Agent    │  ← Декомпозиция на объекты
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Image Gen Agent    │  ← DALL-E 3 / FLUX / Qwen (2D-превью)
└─────────┬───────────┘
          │
    [Пользователь подтверждает]
          │
          ▼
┌─────────────────────┐
│  Generation Agent   │  ← Tripo3D API / Hunyuan3D (локально)
└─────────┬───────────┘
          │
          ▼
┌─────────────────────────────────────┐
│  Intelligent PostProcessing Agent   │
│  ├── Анализ нависаний (24 угла)     │
│  ├── Решение по поддержкам          │
│  └── Оптимальная ориентация         │
└─────────┬───────────────────────────┘
          │
          ▼
    Готовый STL
```

---

## Возможности

| Функция | Описание |
|---|---|
| **Text-to-3D** | Генерация модели по текстовому описанию |
| **2D-превью** | Изображение до дорогостоящего 3D-запроса |
| **Умная постобработка** | ИИ-агент анализирует геометрию и готовит к печати |
| **Мультивью** | Несколько ракурсов → выше качество 3D |
| **Мультиобъектные сцены** | Генерация сложных сцен |
| **MCP-интеграция** | Claude Desktop, Cursor, любой MCP-клиент |
| **Локальные модели** | Hunyuan3D-2, TripoSR, FLUX — без облачных API |
| **Docker-стек** | Полный локальный стек с GPU |

---

## Быстрый старт

### Через Docker (рекомендуется)

```bash
# Готовый образ из GitHub Container Registry
docker pull ghcr.io/teslaproduuction/3d-agent-mcp:latest

cp .env.example .env
# Заполнить .env API-ключами

docker-compose up -d
# → http://localhost:7860
```

### Через UV (быстрее pip в 10–100×)

```bash
# Установить UV
winget install --id=astral-sh.uv -e        # Windows
curl -LsSf https://astral.sh/uv/install.sh | sh  # Linux/macOS

git clone https://github.com/teslaproduuction/3d-agent-mcp.git
cd 3d-agent-mcp
uv venv --python 3.10
uv sync --all-extras

cp .env.example .env
uv run python ui/gradio_app.py
# → http://localhost:7860
```

### Через pip

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows

pip install -r requirements.txt
cp .env.example .env
python ui/gradio_app.py
```

---

## MCP-интеграция

Работает с **Claude Desktop**, **Cursor**, **Windsurf** и любым MCP-клиентом.

### Конфиг Claude Desktop

```json
{
  "mcpServers": {
    "3d-agent": {
      "command": "python",
      "args": ["/path/to/3d-agent-mcp/mcp_server/server.py"],
      "env": {
        "TRIPO_API_KEY": "ваш_ключ",
        "OPENAI_API_KEY": "ваш_ключ"
      }
    }
  }
}
```

### Использование в Claude

```
Пользователь: Сгенерируй подставку для телефона для 3D-печати

Claude: [вызывает generate_3d_model]
✅ Модель сгенерирована и оптимизирована!
   - Файл: outputs/models/phone_stand_optimized.stl
   - Поддержки: не требуются
   - Ориентация: основанием вниз
   - Время печати: ~2ч 15мин
```

**Доступные инструменты MCP:** `generate_3d_model` · `generate_2d_preview` · `analyze_printability` · `plan_scene`

→ [mcp_server/README.md](mcp_server/README.md) — полная документация API

---

## API-ключи

| Ключ | Назначение | Обязательный |
|---|---|---|
| `OPENAI_API_KEY` | DALL-E 3 + GPT для агентов | Для облачного режима |
| `TRIPO_API_KEY` | Генерация 3D (Tripo3D) | Для облачного режима |
| `ANTHROPIC_API_KEY` | Claude как LLM для агентов | Опционально |
| `REPLICATE_API_TOKEN` | SDXL / Flux генерация изображений | Опционально |

> **Локальный режим не требует ключей** — Hunyuan3D + FLUX запускаются через Docker.

---

## Конфигурация

`config.yaml`:

```yaml
default_settings:
  image_generation:
    provider: "local"     # local | dalle3 | sdxl | flux

  generation:
    api_provider: "local" # local | tripo | meshy
    face_limit: 10000

  postprocessing:
    mode: "intelligent"
    auto_orient: true
    max_overhang_angle: 45.0

  printer:
    build_volume: [220, 220, 250]  # Ender 3 / Bambu A1
    nozzle_diameter: 0.4
    material: "PLA"

llm:
  default_provider: "ollama"
  local:
    ollama_models: ["qwen2.5:32b", "qwen2.5:7b"]
```

---

## Структура проекта

```
3d-agent-mcp/
├── agents/                              # ИИ-агенты
│   ├── coordinator.py                   # Оркестратор
│   ├── planner_agent.py                 # Декомпозиция сцены
│   ├── image_generation_agent.py        # 2D-превью
│   ├── generation_agent.py              # 3D API
│   └── intelligent_postprocessing_agent.py
│
├── api_clients/                         # Обёртки API
│   ├── llm_client.py
│   ├── image_api_client.py
│   └── tripo_client.py
│
├── mcp_server/                          # MCP-сервер
├── ui/                                  # Gradio веб-интерфейс
├── postprocessing/                      # Анализ геометрии
├── docker/                              # Локальные Docker-контейнеры
│   ├── hunyuan3d/
│   ├── flux/
│   ├── comfyui/
│   └── nginx/
│
├── tests/
├── config.yaml
├── .env.example
├── docker-compose.yml
└── pyproject.toml
```

---

## Диаграммы

| Диаграмма | Файл |
|---|---|
| Компонентная | [docs/PR/diagrams/01_component.png](docs/PR/diagrams/01_component.png) |
| Последовательности | [docs/PR/diagrams/02_sequence.png](docs/PR/diagrams/02_sequence.png) |
| Активности | [docs/PR/diagrams/03_activity_gci.png](docs/PR/diagrams/03_activity_gci.png) |
| Развёртывания | [docs/PR/diagrams/04_deployment.png](docs/PR/diagrams/04_deployment.png) |
| Классов | [docs/PR/diagrams/05_classes.png](docs/PR/diagrams/05_classes.png) |

---

## Разработка

```bash
pytest tests/
black .
flake8 .
mypy .
```

---

## Дорожная карта

- [ ] Интеграция Meshy API
- [ ] PySLM — физическая генерация поддержек
- [ ] G-code превью перед печатью
- [ ] Библиотека пресетов принтеров
- [ ] Экспорт в OBJ, FBX, GLTF
- [ ] REST API (без Gradio)

---

## Contributing

1. Fork репозитория
2. Создать ветку: `git checkout -b feature/my-feature`
3. Коммит: `git commit -m "feat: добавить функцию"`
4. Push: `git push origin feature/my-feature`
5. Открыть Pull Request

---

## Лицензия

MIT © 2026 — см. [LICENSE](LICENSE)
