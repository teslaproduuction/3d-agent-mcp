# 3D Agent MCP — AI-система генерации 3D-моделей для печати

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![Gradio](https://img.shields.io/badge/Gradio-Web%20UI-FF7C00?logo=gradio)](https://gradio.app)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-5A4FCF)](https://modelcontextprotocol.io)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

Мультиагентная система для генерации 3D-моделей по текстовому описанию с автоматической подготовкой к FDM-печати. Текст → 2D-превью → 3D-модель → оптимизированный STL.

---

## Демонстрация работы

<img src="docs/images/v2_text_to_3d_pipeline.png" alt="Пайплайн генерации" width="100%"/>

*Полный пайплайн: от текстового запроса до готового STL-файла*

---

## Архитектура системы

### Контекст (C4 Level 1)

<img src="docs/images/c4_l1_context.png" alt="Контекстная диаграмма" width="100%"/>

### Контейнеры (C4 Level 2)

<img src="docs/images/c4_l2_containers.png" alt="Диаграмма контейнеров" width="100%"/>

### Технологический стек

<img src="docs/images/v2_tech_stack.png" alt="Технологический стек" width="100%"/>

---

## Ключевые возможности

| Функция | Описание |
|---|---|
| **Text-to-3D** | Генерация 3D-модели по текстовому описанию |
| **2D-превью** | Создание изображения перед дорогостоящей 3D-генерацией |
| **Авто-постобработка** | ИИ-агент анализирует геометрию и готовит модель к печати |
| **Мультиобъектные сцены** | Планирование и генерация сложных сцен |
| **MCP-интеграция** | Использование из Claude Desktop, Cursor и других MCP-клиентов |
| **Docker-стек** | Локальные модели: Hunyuan3D, Flux, Qwen-Image-Edit |

---

## Агентная система

```
User Input
    │
    ▼
Planner Agent          ← Декомпозиция запроса на объекты
    │
    ▼
Image Generation Agent ← 2D-превью (DALL-E 3 / SDXL / Flux)
    │
    ▼ (подтверждение пользователя)
Generation Agent       ← 3D API (Tripo3D / Hunyuan3D)
    │
    ▼
Intelligent PostProcessing Agent
    ├── Анализ геометрии (нависания, полости, ориентация)
    ├── Решение по поддержкам (none / minimal / standard / arc)
    └── Оптимальная ориентация на платформе
    │
    ▼
Print-Ready STL
```

### Агенты

| Агент | Файл | Роль |
|---|---|---|
| Coordinator | `agents/coordinator.py` | Оркестрация пайплайна |
| Planner | `agents/planner_agent.py` | Декомпозиция сцены |
| ImageGen | `agents/image_generation_agent.py` | 2D-превью |
| Generation | `agents/generation_agent.py` | Запросы к 3D API |
| PostProcessing | `agents/intelligent_postprocessing_agent.py` | Подготовка к печати |

---

## Интеллектуальная постобработка

Агент автоматически анализирует каждую модель и выдаёт обоснование:

```
desk_organizer analysis:

✅ Модель можно напечатать без поддержек в рекомендованной ориентации.

Сложность печати: EASY

AI-анализ:
- Сложность геометрии: MEDIUM
- Макс. угол нависания: 38.5°
- Площадь контакта с платформой: 1 250 mm²
- Внутренних полостей не обнаружено
```

---

## Установка

### Вариант 1: UV (рекомендуется, в 10–100× быстрее pip)

```bash
# 1. Установить UV
winget install --id=astral-sh.uv -e        # Windows
curl -LsSf https://astral.sh/uv/install.sh | sh  # Linux/macOS

# 2. Клонировать и настроить
git clone <repository-url>
cd 3dAgentMCP
uv venv --python 3.10
uv sync --all-extras

# 3. Настроить ключи
cp .env.example .env
# Отредактировать .env

# 4. Запустить
uv run python ui/gradio_app.py
```

### Вариант 2: Docker (полный стек с локальными моделями)

```bash
cp .env.example .env
# Отредактировать .env

docker-compose up -d --build
# Интерфейс: http://localhost
```

### Вариант 3: pip (классический)

```bash
python -m venv .venv
source .venv/bin/activate     # Linux/macOS
.venv\Scripts\activate        # Windows

pip install -r requirements.txt
cp .env.example .env
python ui/gradio_app.py       # http://localhost:7860
```

---

## Необходимые API-ключи

| Ключ | Назначение | Обязательный |
|---|---|---|
| `TRIPO_API_KEY` | Генерация 3D (Tripo3D) | Да |
| `OPENAI_API_KEY` | DALL-E 3 + GPT для агентов | Да |
| `ANTHROPIC_API_KEY` | Claude для агентов (альтернатива GPT) | Нет |
| `REPLICATE_API_TOKEN` | SDXL / Flux генерация изображений | Нет |

---

## MCP-интеграция (Claude Desktop / Cursor)

```json
{
  "mcpServers": {
    "3d-agent-generation": {
      "command": "python",
      "args": ["/path/to/3dAgentMCP/mcp_server/server.py"],
      "env": {
        "TRIPO_API_KEY": "your_key",
        "OPENAI_API_KEY": "your_key"
      }
    }
  }
}
```

После настройки в Claude Desktop:

```
User: Сгенерируй подставку для телефона для 3D-печати

Claude: [вызывает инструмент generate_3d_model]
✅ Модель сгенерирована и оптимизирована для печати!
```

Подробнее: [mcp_server/README.md](mcp_server/README.md)

---

## Структура проекта

```
3dAgentMCP/
├── agents/                          # ИИ-агенты
│   ├── coordinator.py               # Оркестрация
│   ├── planner_agent.py             # Планирование сцены
│   ├── image_generation_agent.py    # 2D-превью
│   ├── generation_agent.py          # 3D-генерация
│   └── intelligent_postprocessing_agent.py
│
├── api_clients/                     # Обёртки над API
│   ├── llm_client.py                # OpenAI / Anthropic
│   ├── image_api_client.py          # DALL-E / SDXL / Flux
│   └── tripo_client.py              # Tripo3D
│
├── mcp_server/                      # MCP-сервер
│   ├── server.py
│   └── README.md
│
├── ui/                              # Веб-интерфейс (Gradio)
│   ├── gradio_app.py
│   └── tabs/, handlers/, components/
│
├── utils/                           # Вспомогательные модули
│   ├── config.py
│   ├── file_manager.py
│   ├── mesh_analyzer.py
│   └── logger.py
│
├── postprocessing/                  # Постобработка моделей
├── docker/                          # Docker-образы для локальных моделей
│   ├── hunyuan3d/                   # Hunyuan3D (локальная 3D-генерация)
│   ├── flux/                        # Flux (локальная генерация изображений)
│   ├── comfyui/                     # ComfyUI
│   └── nginx/                       # Обратный прокси
│
├── tests/                           # Тесты
├── config.yaml                      # Основная конфигурация
├── .env.example                     # Пример переменных окружения
├── docker-compose.yml               # Docker Compose
├── pyproject.toml                   # Зависимости (uv/pip)
└── requirements.txt
```

---

## Конфигурация

Основные параметры в `config.yaml`:

```yaml
default_settings:
  image_generation:
    provider: "dalle3"        # dalle3 | sdxl | flux | qwen

  generation:
    api_provider: "tripo"     # tripo | hunyuan3d
    face_limit: 10000

  postprocessing:
    mode: "intelligent"       # агент принимает решения сам
    auto_orient: true
    max_overhang_angle: 45.0

  printer:
    build_volume: [220, 220, 250]   # mm (Ender 3 / Bambu A1)
    nozzle_diameter: 0.4
    material: "PLA"
```

---

## Разработка

```bash
# Тесты
pytest tests/

# Форматирование
black .

# Линтинг
flake8 .
```

---

## Дорожная карта

- [ ] Интеграция Meshy API
- [ ] PySLM — физическая генерация поддержек
- [ ] Режим мульти-вью для улучшения качества 3D
- [ ] Экспорт в OBJ, FBX, GLTF
- [ ] Пресеты принтеров

---

## Технологии

- **Tripo3D** — облачная генерация 3D-моделей
- **Hunyuan3D** — локальная 3D-генерация (Docker)
- **OpenAI DALL-E 3 / GPT** — изображения и агенты
- **Flux / SDXL** — альтернативная генерация изображений
- **Trimesh** — анализ 3D-геометрии
- **Gradio** — веб-интерфейс
- **MCP (Anthropic)** — протокол интеграции с ИИ-клиентами

---

*Выпускная квалификационная работа — ЯГТУ, 2026*
