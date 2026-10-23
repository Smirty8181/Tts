# Twitch Sentinel

Локальная панель мониторинга Twitch с FastAPI-бэкендом и Vue-интерфейсом. Проект включает подключение к Twitch, мониторинг чата, работу с LLM-провайдерами, память и интеграции с OBS и JeetBot.

## Требования

- Python 3.11+
- Node.js 22+
- npm

## Быстрый запуск в Windows

1. Создайте `backend\.env` на основе `backend\.env.example` и заполните только нужные ключи.
   Для `LOCAL_ENCRYPTION_KEY` сгенерируйте значение командой:

   ```powershell
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Сохраните ключ в безопасном месте и не меняйте его после сохранения учётных данных: без прежнего ключа их нельзя расшифровать.

2. Запустите `start_all.bat`. Скрипт подготовит виртуальное окружение и зависимости, создаст локальную базу данных и запустит backend и frontend.
3. Откройте <http://localhost:5173>.

Для запуска только интерфейса используйте `start.bat`.

## Ручной запуск

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python init_db.py
.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Frontend в отдельном терминале:

```powershell
cd frontend
npm ci
npm run dev -- --host 0.0.0.0
```

Откройте <http://localhost:5173>. Для настройки адреса API и Twitch OAuth используйте `frontend\.env.example` как шаблон.

## Docker Compose

```powershell
Copy-Item backend\.env.example backend\.env
docker compose up --build
```

Frontend будет доступен на порту `5173`, backend — на порту `8000`. Перед запуском настройте `backend\.env`; не помещайте реальные ключи и токены в репозиторий.

## Проверки

Backend-тесты (сначала установите `pytest` в виртуальное окружение):

```powershell
cd backend
.\.venv\Scripts\python -m pip install pytest
.\.venv\Scripts\python -m pytest -q
```

Сборка frontend:

```powershell
npm run build
```

Локальные базы, `.env`, виртуальные окружения, зависимости и результаты сборки исключены из Git.
