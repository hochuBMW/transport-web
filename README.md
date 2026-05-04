# Transport Web

Проект состоит из двух частей: бэкенда на Python (FastAPI) и фронтенда на Vue 3 (Vite).

## Требования
- Python 3.8+
- Node.js (рекомендуется версия 18+)
- npm (поставляется вместе с Node.js)

## 1. Запуск Бэкенда

Бэкенд находится в папке `backend` и построен с использованием FastAPI.

1. Откройте терминал и перейдите в директорию бэкенда:
   ```bash
   cd backend
   ```

2. (Рекомендуется) Создайте и активируйте виртуальное окружение:
   - **Windows:**
     ```bash
     python -m venv .venv
     .venv\Scripts\activate
     ```
   - **macOS/Linux:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

4. Запустите сервер для backend:
   ```bash
   python main.py
   ```

Сервер бэкенда будет доступен по адресу: http://127.0.0.1:8000
Документация Swagger (API): http://127.0.0.1:8000/docs

## 2. Запуск Фронтенда

Фронтенд находится в папке `frontend` и использует Vue 3 + Vite.

1. Откройте новый терминал и перейдите в директорию фронтенда:
   ```bash
   cd frontend
   ```

2. Установите зависимости:
   ```bash
   npm install
   ```

3. Запустите сервер для разработки:
   ```bash
   npm run dev
   ```

Сервер фронтенда обычно запускается по адресу http://localhost:5173 (точный адрес будет выведен в терминале после запуска команды).

## Порядок запуска
Для корректной работы приложения необходимо запустить обе части приложения одновременно в разных окнах терминала. Убедитесь, что бэкенд сервер успешно запущен, прежде чем осуществлять запросы с фронтенда.

## Фоновый сборщик IrkBus (daily rotation)

В проект добавлен отдельный модуль сборщика: `backend/ingest/irkbus`.
Он работает независимо от FastAPI, собирает снимки в течение дня и ротирует файлы по дате.

### Быстрый запуск

1. Перейдите в папку backend:
   ```bash
   cd backend
   ```
2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
3. Создайте `backend/.env` из примера и задайте нужные параметры:
   ```bash
   copy .env.example .env
   ```
4. Запустите один цикл (проверка):
   ```bash
   python -m ingest.irkbus.run --once --no-db
   ```
5. Запустите в фоне (непрерывно):
   ```bash
   python -m ingest.irkbus.run
   ```

### Что сохраняется

- `data/irkbus/raw/raw_YYYY-MM-DD.jsonl` — сырые ответы API по каждому опросу.
- `data/irkbus/features/features_YYYY-MM-DD.jsonl` — нормализованные GeoJSON точки.
- `data/irkbus/latest.geojson` — последний снимок как FeatureCollection.
- `data/irkbus/logs/collector.log` — логи работы сборщика.

### Переменные окружения (основные)

- `IRKBUS_ROUTES` — список маршрутов, например `37-0,36-0`.
- `IRKBUS_POLL_INTERVAL_SEC` — интервал опроса в секундах (по умолчанию `10`).
- `IRKBUS_EMPTY_STREAK_REFRESH` — через сколько пустых ответов обновлять сессию (по умолчанию `6`).
- `IRKBUS_TIMEZONE` — часовой пояс источника времени (по умолчанию `Asia/Irkutsk`).
- `IRKBUS_DATA_DIR` — куда писать файлы (по умолчанию `data/irkbus`).
- `IRKBUS_COOKIE` — стартовый cookie-header (опционально), если хотите запустить с уже рабочей сессией.
- `IRKBUS_DB_DSN` — DSN для PostgreSQL/PostGIS.
- `IRKBUS_USE_DB` — включить запись в БД (`true`/`false`).

Сборщик сам обновляет `PHPSESSID` через запрос на главную страницу `irkbus.ru` и не требует ручного копирования cookie из DevTools.

Если провайдер возвращает пустые снимки (`buses=0`), можно передать вручную рабочий cookie:
- через env `IRKBUS_COOKIE`,
- либо через UI-вкладку "Парсер" при нажатии "Запустить".
