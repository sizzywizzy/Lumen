SHELL := /bin/sh

PYTHON ?= python3
NODE ?= node
NPM ?= npm
VENV ?= backend/.venv
PIP := $(VENV)/bin/pip
PYTHON_BIN := $(VENV)/bin/python
PYDOCTOR := $(PYTHON_BIN) -m pydoctor

.PHONY: all install setup test build clean dev run backend frontend docs help

all: install setup test build

install: $(VENV)/bin/activate frontend/node_modules

$(VENV)/bin/activate: backend/requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt

frontend/node_modules: frontend/package.json frontend/package-lock.json
	$(NPM) --prefix frontend ci

setup:
	@if [ -f .env.example ] && [ ! -f .env ]; then \
		cp .env.example .env; \
		printf '%s\n' 'Created .env from .env.example; add credentials if needed.'; \
	fi

test: install
	$(PYTHON_BIN) -m compileall -q backend
	$(PYTHON_BIN) backend/run_demo.py --project PROJ_NEON_NIGHTS --mode indie

build: install
	$(NPM) --prefix frontend run build

dev: install
	@printf '%s\n' 'Run these commands in separate terminals:'
	@printf '%s\n' '  make backend'
	@printf '%s\n' '  make frontend'

run:
	docker compose up --build

backend: install
	$(PYTHON_BIN) -m uvicorn main:app --app-dir backend --reload --port 8000

frontend: install
	$(NPM) --prefix frontend run dev

docs: install
	$(PIP) install --upgrade pydoctor
	$(PYDOCTOR) --make-html \
		--html-output=./docs \
		--project-name="CineNode" \
		backend/core \
		backend/domains \
		backend/services \
		backend/main.py \
		backend/run_demo.py

clean:
	rm -rf $(VENV) frontend/node_modules frontend/dist
	find backend -type d -name __pycache__ -prune -exec rm -rf {} +

help:
	@printf '%s\n' \
		'Available targets:' \
		'  make all       Install dependencies, set up the environment, test, and build' \
		'  make install   Install Python and frontend dependencies' \
		'  make setup     Create .env from .env.example when .env is missing' \
		'  make test      Compile the backend and run the full mock pipeline' \
		'  make build     Build the frontend for production' \
		'  make dev       Show commands for starting backend and frontend development servers' \
		'  make run       Start the full backend and frontend stack with Docker Compose' \
		'  make backend   Start the backend development server on port 8000' \
		'  make frontend  Start the frontend development server' \
		'  make docs      Install Pydoctor and generate HTML API documentation' \
		'  make clean     Remove generated dependencies, builds, and caches'