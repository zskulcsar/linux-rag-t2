# Root Makefile for linux-rag-t2 tooling convenience.

SHELL := /usr/bin/env bash

PYTHON_SRC_DIRS := services tests
PYTEST_UNIT_DIR := tests/python/unit
PYTEST_INTEGRATION_DIR := tests/python/integration
PYTEST_CONTRACT_DIR := tests/python/contract
MKDOCS_CONFIG := mkdocs.yml
MKDOCS_SITE_DIR := site
UV_ENV := PYTHONPATH=$(CURDIR) UV_CACHE_DIR=$(CURDIR)/.uv_cache
UV_PYTEST := $(UV_ENV) uv run --project services/rag_backend pytest
GO_ENV := GOCACHE=$(CURDIR)/.gocache
GO_TEST := $(GO_ENV) go test -v
DIST_DIR := $(CURDIR)/dist
DIST_BIN_DIR := $(DIST_DIR)/bin
PY_BUILD_DIR := $(DIST_DIR)/python_build
PREFIX ?= /usr/local
DESTDIR ?=

GOFMT_PATHS := $(shell find cli tests -type f -name '*.go' -not -path '*/vendor/*' 2>/dev/null)

.PHONY: help fmt fmt-go fmt-python lint lint-go lint-python typecheck typecheck-go \
		test test-go test-go-unit test-go-contract \
		test-python test-python-unit test-python-integration test-python-contract \
		security security-python security-go \
		docs docs-serve docs-cli docs-backend build-go \
		package package-go package-python install install-go install-python \
		clean

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

typecheck-go: ## Execute go vet across all Go packages.
	GO111MODULE=on $(GO_ENV) go vet ./...

security: security-python security-go ## Run dependency/security audits for Python and Go modules.

security-python: ## Run pip-audit against the backend project.
	$(UV_ENV) uv run --project services/rag_backend --with pip-audit pip-audit

security-go: ## Run govulncheck against the Go modules (ragman/ragadmin).
	@if [ -d "$(CURDIR)/cli/ragman" ]; then \
		( cd cli/ragman && GO111MODULE=on $(GO_ENV) go run golang.org/x/vuln/cmd/govulncheck@latest ./... ); \
	else \
		echo "Skipping ragman govulncheck; module missing."; \
	fi
	@if [ -d "$(CURDIR)/cli/ragadmin" ]; then \
		( cd cli/ragadmin && GO111MODULE=on $(GO_ENV) go run golang.org/x/vuln/cmd/govulncheck@latest ./... ); \
	else \
		echo "Skipping ragadmin govulncheck; module missing."; \
	fi

test: test-go test-python ## Run all test suites.

test-go: test-go-unit test-go-contract ## Run all Go tests.

test-go-unit: ## Execute Go unit tests for CLI modules.
	$(GO_TEST) ./tests/go/unit/ipc/... ./tests/go/unit/ragman/... 

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

build-go: ## Builds the go binaries
	go build -o ./bin/ragman ./cli/ragman
	go build -o ./bin/ragadmin ./cli/ragadmin

run-backend: ## Runs the backend launcher with local defaults
	@mkdir -p $(CURDIR)/tmp/dev
	uv run python -m services.rag_backend.main \
		--config "$(CURDIR)/docs/install/config/ragcli-config.yaml" \
		--socket "$(CURDIR)/tmp/dev/backend.sock" \
		--weaviate-url "http://localhost:8080" \
		--ollama-url "http://localhost:11434" \
		--phoenix-url "http://localhost:6006" \
		--log-level "INFO"

package: package-go package-python ## Build Go CLIs and rag_backend executable into dist/bin.

package-go: ## Build Go binaries into dist/bin for distribution.
	@mkdir -p $(DIST_BIN_DIR)
	@if find ./cli/ragman -name '*.go' -print -quit | grep -q .; then \
		echo "Building ragman..."; \
		GO111MODULE=on $(GO_ENV) go build -o $(DIST_BIN_DIR)/ragman ./cli/ragman; \
	else \
		echo "Skipping ragman build; no Go sources found."; \
	fi
	@if find ./cli/ragadmin -name '*.go' -print -quit | grep -q .; then \
		echo "Building ragadmin..."; \
		GO111MODULE=on $(GO_ENV) go build -o $(DIST_BIN_DIR)/ragadmin ./cli/ragadmin; \
	else \
		echo "Skipping ragadmin build; no Go sources found."; \
	fi

package-python: ## Build the rag_backend zipapp executable with bundled dependencies.
	@mkdir -p $(DIST_BIN_DIR)
	rm -rf $(PY_BUILD_DIR)
	mkdir -p $(PY_BUILD_DIR)/project
	cp -R services $(PY_BUILD_DIR)/project/
	cp services/rag_backend/pyproject.toml $(PY_BUILD_DIR)/project/
	cd $(PY_BUILD_DIR)/project && $(UV_ENV) uv run --with build python -m build --wheel --outdir $(PY_BUILD_DIR)
	@WHEEL="$$(ls $(PY_BUILD_DIR)/rag_backend-*.whl $(PY_BUILD_DIR)/rag-backend-*.whl 2>/dev/null | head -n1)"; \
	if [ -z "$$WHEEL" ]; then \
		echo "Unable to locate built rag-backend wheel in $(PY_BUILD_DIR)"; \
		exit 1; \
	fi; \
	rm -rf $(PY_BUILD_DIR)/app && mkdir -p $(PY_BUILD_DIR)/app; \
	$(UV_ENV) uv pip install --quiet --target $(PY_BUILD_DIR)/app "$$WHEEL"; \
	$(UV_ENV) uv run python -m zipapp $(PY_BUILD_DIR)/app \
		-m services.rag_backend.main:main \
		-p "/usr/bin/env python3" \
		-o $(DIST_BIN_DIR)/rag_backend; \
	chmod +x $(DIST_BIN_DIR)/rag_backend

install: install-go install-python ## Install compiled binaries under $(PREFIX)/bin.

install-go: package-go ## Install Go CLIs into $(PREFIX)/bin.
	install -d $(DESTDIR)$(PREFIX)/bin
	if [ -f $(DIST_BIN_DIR)/ragman ]; then \
		install -m 0755 $(DIST_BIN_DIR)/ragman $(DESTDIR)$(PREFIX)/bin/ragman; \
	else \
		echo "Warning: ragman binary missing; skipping install."; \
	fi
	if [ -f $(DIST_BIN_DIR)/ragadmin ]; then \
		install -m 0755 $(DIST_BIN_DIR)/ragadmin $(DESTDIR)$(PREFIX)/bin/ragadmin; \
	else \
		echo "Warning: ragadmin binary missing; skipping install."; \
	fi

install-python: package-python ## Install rag_backend executable into $(PREFIX)/bin.
	install -d $(DESTDIR)$(PREFIX)/bin
	install -m 0755 $(DIST_BIN_DIR)/rag_backend $(DESTDIR)$(PREFIX)/bin/rag_backend

clean: ## Remove generated build artifacts and caches.
	rm -rf \
		$(DIST_DIR) \
		$(CURDIR)/bin \
		$(CURDIR)/tmp/install \
		$(CURDIR)/tmp/test \
		$(CURDIR)/tmp/ragcli \
		$(CURDIR)/.gocache \
		$(CURDIR)/.uv_cache \
		$(CURDIR)/.pytest_cache \
		$(CURDIR)/.ruff_cache \
		$(CURDIR)/.mypy_cache \
		$(CURDIR)/services/rag_backend/.venv
