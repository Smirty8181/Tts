#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
(cd frontend && npm install)
backend/.venv/bin/python backend/init_db.py
(trap 'kill 0' SIGINT; backend/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend & (cd frontend && npm run dev -- --host 0.0.0.0) & wait)
