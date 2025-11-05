# Root Makefile for linux-rag-t2 tooling convenience.

SHELL := /usr/bin/env bash

PYTHON_SRC_DIRS := services tests
PYTEST_UNIT_DIR := tests/python/unit
PYTEST_INTEGRATION_DIR := tests/python/integration
PYTEST_CONTRACT_DIR := tests/python/contract
MKDOCS_CONFIG := mkdocs.yml
MKDOCS_SITE_DIR := docs/site
UV_ENV := PYTHONPATH=$(CURDIR) UV_CACHE_DIR=$(CURDIR)/.uv_cache
UV_PYTEST := $(UV_ENV) uv run --project services/rag_backend pytest
GO_ENV := GOCACHE=$(CURDIR)/.gocache
GO_TEST := $(GO_ENV) go test -v

GOFMT_PATHS := $(shell find cli tests -type f -name '*.go' -not -path '*/vendor/*' 2>/dev/null)

.PHONY: help fmt fmt-go fmt-python lint lint-go lint-python typecheck \
	test test-go test-go-unit test-go-contract \
	test-python test-python-unit test-python-integration test-python-contract \
	docs docs-serve docs-cli docs-backend

help: ## List available make targets with descriptions.
	@printf "Available targets:\n\n"
	@grep -hE '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"} {printf "  %-24s %s\n", $$1, $$2}' | sort

fmt: fmt-go fmt-python ## Format Go and Python sources.

fmt-go: ## Run gofmt over Go sources.
	@if [ -n "$(GOFMT_PATHS)" ]; then \
		gofmt -w $(GOFMT_PATHS); \
	else \
		echo "No Go files to format."; \
	fi

fmt-python: ## Format Python sources using Ruff.
	uv run ruff format $(PYTHON_SRC_DIRS)

lint: lint-go lint-python ## Run Go and Python linters.

lint-go: ## Run golangci-lint across all modules.
	golangci-lint run ./...

lint-python: ## Run Ruff lint checks.
	uv run ruff check $(PYTHON_SRC_DIRS)

typecheck: ## Execute Python type checking with mypy.
	uv run mypy services/rag_backend

test: test-go test-python ## Run all test suites.

test-go: test-go-unit test-go-contract ## Run all Go tests.

test-go-unit: ## Execute Go unit tests for CLI modules.
	$(GO_TEST) ./tests/go/unit/ipc/...

test-go-contract: ## Execute Go contract tests.
	$(GO_TEST) ./tests/go/contract/...

test-python: test-python-unit test-python-integration test-python-contract ## Run all Python tests.

test-python-unit: ## Run Python unit tests.
	@if [ -d "$(PYTEST_UNIT_DIR)" ]; then \
		if ! $(UV_PYTEST) $(PYTEST_UNIT_DIR); then \
			status=$$?; \
			if [ $$status -ne 5 ]; then exit $$status; fi; \
			echo "pytest reported no tests in $(PYTEST_UNIT_DIR); continuing."; \
		fi; \
	else \
		echo "Skipping $(PYTEST_UNIT_DIR); directory missing."; \
	fi

test-python-integration: ## Run Python integration tests.
	@if [ -d "$(PYTEST_INTEGRATION_DIR)" ]; then \
		if ! $(UV_PYTEST) $(PYTEST_INTEGRATION_DIR); then \
			status=$$?; \
			if [ $$status -ne 5 ]; then exit $$status; fi; \
			echo "pytest reported no tests in $(PYTEST_INTEGRATION_DIR); continuing."; \
		fi; \
	else \
		echo "Skipping $(PYTEST_INTEGRATION_DIR); directory missing."; \
	fi

test-python-contract: ## Run Python contract tests.
	@if [ -d "$(PYTEST_CONTRACT_DIR)" ]; then \
		if ! $(UV_PYTEST) $(PYTEST_CONTRACT_DIR); then \
			status=$$?; \
			if [ $$status -ne 5 ]; then exit $$status; fi; \
			echo "pytest reported no tests in $(PYTEST_CONTRACT_DIR); continuing."; \
		fi; \
	else \
		echo "Skipping $(PYTEST_CONTRACT_DIR); directory missing."; \
	fi

docs: docs-cli docs-backend ## Build MkDocs documentation into docs/site.
	@if [ -f "$(MKDOCS_CONFIG)" ]; then \
		mkdir -p $(MKDOCS_SITE_DIR); \
		uv run mkdocs build --config-file $(MKDOCS_CONFIG) --site-dir $(MKDOCS_SITE_DIR); \
	else \
		echo "Skipping documentation build; $(MKDOCS_CONFIG) not found."; \
	fi

docs-serve: docs-cli docs-backend ## Serve MkDocs documentation locally for preview.
	@if [ -f "$(MKDOCS_CONFIG)" ]; then \
		uv run mkdocs serve --config-file $(MKDOCS_CONFIG); \
	else \
		echo "Skipping documentation server; $(MKDOCS_CONFIG) not found."; \
	fi

docs-cli: ## Generate Markdown documentation for Go CLIs.
	./scripts/docs/generate_cli_docs.sh

docs-backend: ## Generate documentation for the Python backend service.
	@if command -v uv >/dev/null 2>&1; then \
		uv run python scripts/docs/generate_backend_docs.py; \
	else \
		python scripts/docs/generate_backend_docs.py; \
	fi

helper.clean-go-cache: ## Cleares the go cache
	go clean -cache
