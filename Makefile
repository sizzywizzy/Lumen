SHELL := /bin/sh

PYTHON ?= python3
NODE ?= node
NPM ?= npm
VENV ?= backend/.venv
PIP := $(VENV)/bin/pip
PYTHON_BIN := $(VENV)/bin/python

.PHONY: all install setup test build clean dev run backend frontend docs help check-tools

all: install setup test build

check-tools:
	@command -v $(PYTHON) >/dev/null 2>&1 || { echo "Error: $(PYTHON) not found. Please install Python 3."; exit 1; }
	@command -v $(NODE) >/dev/null 2>&1 || { echo "Error: $(NODE) not found. Please install Node.js."; exit 1; }
	@command -v $(NPM) >/dev/null 2>&1 || { echo "Error: $(NPM) not found. Please install npm."; exit 1; }

install: check-tools $(VENV)/bin/activate frontend/node_modules

$(VENV)/bin/activate: backend/requirements.txt
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
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
	@$(PIP) show pydoctor >/dev/null 2>&1 || $(PIP) install --upgrade pydoctor
	$(PYTHON_BIN) -m pydoctor --make-html \
		--html-output=./docs \
		--project-name="CineNode" \
		backend/core \
		backend/domains \
		backend/services \
		backend/main.py \
		backend/run_demo.py

clean:
	rm -rf $(VENV) frontend/node_modules frontend/dist
	find backend -type d -name __pycache__ -delete
	find backend -type f -name '*.pyc' -delete

help:
	@printf '%s\n' \
		'Available targets:' \
		'  make all         Install dependencies, set up the environment, test, and build' \
		'  make check-tools Verify required tools (python3, node, npm) are installed' \
		'  make install     Install Python and frontend dependencies' \
		'  make setup       Create .env from .env.example when .env is missing' \
		'  make test        Compile the backend and run the full mock pipeline' \
		'  make build       Build the frontend for production' \
		'  make dev         Show commands for starting backend and frontend development servers' \
		'  make run         Start the full backend and frontend stack with Docker Compose' \
		'  make backend     Start the backend development server on port 8000' \
		'  make frontend    Start the frontend development server' \
		'  make docs        Generate HTML API documentation (pydoctor)' \
		'  make clean       Remove generated dependencies, builds, and caches'