"""
Main entry point for 3D Agent Generation System
"""
import argparse
import os

import gradio as gr
import uvicorn
from fastapi import FastAPI

from ui.gradio_app import GradioInterface
from utils.config import load_config
from utils.logger import setup_logger


def main():
    """Main function to launch the application"""
    parser = argparse.ArgumentParser(
        description="AI 3D Агент - Система генерации моделей"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Хост для привязки (по умолчанию: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Порт для привязки (по умолчанию: 7860)"
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Создать публичную ссылку для доступа"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Включить отладочное логирование"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Путь к файлу конфигурации (по умолчанию: config.yaml)"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.debug else "INFO"
    logger = setup_logger(
        name="3d_agent",
        level=log_level,
        log_file="logs/3d_agent.log",
        console=True
    )

    logger.info("=" * 60)
    logger.info("Запуск системы генерации 3D моделей")
    logger.info("=" * 60)

    # Load configuration
    try:
        config = load_config(args.config)
        logger.info("Конфигурация успешно загружена")
    except Exception as e:
        logger.error(f"Не удалось загрузить конфигурацию: {e}")
        logger.error("Убедитесь, что config.yaml существует и API ключи настроены")
        return

    # Validate API keys only when cloud providers are actually in use
    llm_provider = config.get('llm.default_provider', 'openai')
    image_provider = config.get('default_settings.image_generation.provider', 'dalle3')
    gen_provider = config.get('default_settings.generation.api_provider', 'tripo')
    all_local = (llm_provider == 'ollama' and image_provider == 'local' and gen_provider == 'local')

    if not all_local:
        required_keys = []
        if gen_provider not in ('local',):
            required_keys.append('tripo')
        if image_provider not in ('local',) or llm_provider not in ('ollama',):
            required_keys.append('openai')

        missing_keys = []
        for key in required_keys:
            try:
                config.get_api_key(key)
            except ValueError:
                missing_keys.append(key)

        if missing_keys:
            logger.error(f"Отсутствуют необходимые API ключи: {', '.join(missing_keys)}")
            logger.error("Установите их в config.yaml или как переменные окружения")
            logger.error("См. .env.example для списка необходимых ключей")
            return
    else:
        logger.info("Режим полностью локальных провайдеров — проверка API ключей пропущена")

    # Feature flag: Choose coordinator (AutoGen vs Legacy)
    use_autogen = config.get('use_autogen', False)

    if use_autogen:
        logger.info("🚀 Использую AutoGen агенты (новая система)")
        from agents.autogen.autogen_coordinator import AutoGenCoordinator
        coordinator = AutoGenCoordinator(config)
    else:
        logger.info("📦 Использую legacy агенты (текущая система)")
        from agents.coordinator import CoordinatorAgent
        coordinator = CoordinatorAgent(config)

    logger.info(f"Координатор инициализирован: {coordinator}")

    # Warm up rembg at startup so first background removal request is not slow.
    warmup_enabled = os.getenv("REMBG_WARMUP_ON_START", "1").strip().lower() not in {"0", "false", "no"}
    if warmup_enabled:
        try:
            from utils.image_processor import warmup_rembg_session
            elapsed = warmup_rembg_session()
            logger.info(f"Warmup удаления фона завершен за {elapsed:.2f}с")
        except Exception as e:
            logger.warning(f"Не удалось прогреть модель удаления фона: {e}")

    # Create and launch Gradio interface
    logger.info("Инициализация интерфейса Gradio...")
    interface = GradioInterface(coordinator=coordinator)

    logger.info("Инициализация упрощённого интерфейса ЯГТУ...")
    from ui.ystu_app import GradioInterfaceYSTU
    ystu_interface = GradioInterfaceYSTU(coordinator=coordinator)

    logger.info(f"Запуск веб-интерфейса на http://{args.host}:{args.port}")
    logger.info(f"  Основной интерфейс:  http://{args.host}:{args.port}/")
    logger.info(f"  Интерфейс ЯГТУ:      http://{args.host}:{args.port}/ystu")
    if args.share:
        logger.info("Создание публичной ссылки...")

    try:
        import threading

        queue_enabled = os.getenv("GRADIO_ENABLE_QUEUE", "1").strip().lower() not in {"0", "false", "no"}
        try:
            queue_limit = int(os.getenv("GRADIO_QUEUE_CONCURRENCY", "1"))
        except (TypeError, ValueError):
            queue_limit = 1
        try:
            queue_max_size = int(os.getenv("GRADIO_QUEUE_MAX_SIZE", "32"))
        except (TypeError, ValueError):
            queue_max_size = 32

        # Build both demos in the main thread to avoid empty Blocks config in worker thread.
        ystu_demo = ystu_interface.build_interface()
        main_demo = interface.build_interface()

        if queue_enabled:
            ystu_demo.queue(
                status_update_rate=1,
                max_size=max(1, queue_max_size),
                default_concurrency_limit=max(1, queue_limit),
            )
            main_demo.queue(
                status_update_rate=1,
                max_size=max(1, queue_max_size),
                default_concurrency_limit=max(1, queue_limit),
            )

        # ── YSTU interface on port 7861 (launched in background thread) ──────
        def launch_ystu():
            try:
                logger.info("Запуск ЯГТУ-интерфейса на порту 7861 (root_path=/ystu)...")
                ystu_demo.launch(
                    server_name=args.host,
                    server_port=7861,
                    root_path="/ystu",
                    prevent_thread_lock=False,
                )
            except Exception as e:
                logger.error(f"Ошибка запуска ЯГТУ-интерфейса: {e}")

        ystu_thread = threading.Thread(target=launch_ystu, daemon=True)
        ystu_thread.start()

        main_demo.launch(server_name=args.host, server_port=args.port)

    except KeyboardInterrupt:
        logger.info("Завершение работы...")
    except Exception as e:
        logger.error(f"Ошибка при запуске приложения: {e}")


if __name__ == "__main__":
    main()
