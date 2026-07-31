# Makefile for kube-oidc-issuer-reflector

ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

VENV_DIR := $(shell if [ -d "$(ROOT_DIR)/.venv" ]; then printf "%s" "$(ROOT_DIR)/.venv"; elif [ -d "$(ROOT_DIR)/venv" ]; then printf "%s" "$(ROOT_DIR)/venv"; else printf "%s" "$(ROOT_DIR)/.venv"; fi)

VENV_PYTHON := $(shell if [ -x "$(VENV_DIR)/bin/python" ]; then printf "%s" "$(VENV_DIR)/bin/python"; else command -v python3 || command -v python; fi)
VENV_PIP := $(shell if [ -x "$(VENV_DIR)/bin/pip" ]; then printf "%s" "$(VENV_DIR)/bin/pip"; else printf "%s" "$(VENV_PYTHON) -m pip"; fi)

.PHONY: help install install-dev test test-cov lint format format-check type-check security docker-build docker-run all clean test-integration

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install package
	$(VENV_PIP) install -e .

install-dev: ## Install package with development dependencies
	$(VENV_PIP) install -e ".[dev]"

test: ## Run tests (via tox)
	$(VENV_PYTHON) -m tox -e py

test-cov: ## Run tests with coverage (via tox)
	$(VENV_PYTHON) -m tox -e py

test-integration: ## Run integration tests with local kind cluster
	bash scripts/run-integration-tests.sh

lint: ## Run linting
	$(VENV_PYTHON) -m ruff check .
	$(VENV_PYTHON) -m pyright

format: ## Format code
	$(VENV_PYTHON) -m ruff format .

format-check: ## Check code formatting
	$(VENV_PYTHON) -m ruff format --check .

type-check: ## Run type checking
	$(VENV_PYTHON) -m mypy app
	$(VENV_PYTHON) -m pyright

security: ## Run security scan
	$(VENV_PYTHON) -m semgrep scan --config auto app/ || true

docker-build: ## Build Docker image
	docker build -t kube-oidc-issuer-reflector:latest .

docker-run: ## Run Docker container
	docker run -p 8080:8080 \
		-e DEFAULT_RATE_LIMIT="10 per second" \
		kube-oidc-issuer-reflector:latest

all: format-check lint type-check test ## Run all checks (full CI pipeline)

clean: ## Clean up generated files
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache .pyright htmlcov .coverage coverage.xml coverage_html
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
