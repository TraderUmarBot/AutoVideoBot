# AutoVideoBot

Автогенератор видео через Telegram.

## Файлы
- `main.py` — основной бот
- `requirements.txt` — python зависимости
- `Dockerfile` — для развёртывания
- `docker-compose.yml` — локальное тестирование
- `jobs.db` — SQLite (создаётся автоматически)

## Переменные окружения
- `TELEGRAM_TOKEN` — **обязательно**
- `OPENAI_API_KEY` — опционально (лучшие сценарии)
- `REPLICATE_API_TOKEN` — опционально (для изображений, нужно доработать реализацию)
- `STABILITY_API_KEY` — опционально
- `ELEVENLABS_API_KEY` — опционально (TTS)
- `FREE_JOBS_PER_USER` — сколько бесплатных запросов/пользователь (по умолчанию 3)

## Запуск локально
1. Склонируй репозиторий.
2. Создай `.env` с TELEGRAM_TOKEN.
3. `docker-compose up --build` — или:
   - `pip install -r requirements.txt`
   - `python main.py`

## Развёртывание на Render
- Создай новый Docker Service, подключи GitHub репозиторий.
- В Render -> Environment -> добавь секрет `TELEGRAM_TOKEN` (и другие при наличии).
- Деплой.

## Замечания / улучшения
- Реальные интеграции с Replicate / Stability нужно дописать под конкретные модели (version id, polling).
- Для масштабирования лучше вынести сборку видео в отдельный воркер (Redis/RQ/Celery).
- Для платного доступа подключи Stripe / Telegram Payments и храни пользователей/подписки.
- Хранение видео: сейчас файлы в /tmp; для долговременного хранения подключите S3.
