.PHONY: install backend frontend build schema

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev -- --port 5173

build:
	cd frontend && npm run build
	cd backend && .venv/bin/python -m compileall app

schema:
	curl http://127.0.0.1:8000/api/schema/tables

