# Root Makefile for linux-rag-t2 tooling convenience.

# Common
SHELL := /usr/bin/env bash
MKDOCS_CONFIG := mkdocs.yml
MKDOCS_SITE_DIR := site
DESTDIR ?= /usr/local

# Python
PY_ROOT := ./backend
BE_SRC = $(PY_ROOT)/src
PYTHON_SRC_DIRS := backend/src tests

# Golang
GO_ENV := GOCACHE=$(CURDIR)/.gocache
GO = GO111MODULE=on $(GO_ENV) go
GO_MODULE_DIRS := cli/ragman cli/shared tests/go


## Default
help: ## List available make targets with descriptions.
	@printf "\nuv is a hard dependency; Install from https://docs.astral.sh/uv/ if you haven't done so already.\n\n"
	@printf "Available targets:\n"
	@grep -hE '.*##\s' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"} {printf "  %-16s %s\n", $$1, $$2}'

## Environment management
venv: ## Create the python virtual environment and download all dependencies
	@test -d $(PY_ROOT)/.venv || uv venv  --directory $(PY_ROOT) --prompt backend .venv
	@uv pip install --directory $(PY_ROOT) --python .venv --upgrade pip
	@uv sync --directory $(PY_ROOT)

clean: ## Removes all generated and downloaded artifacts; returns the repo to it's cloned state (without reversing file modifications)
	@rm -rf \
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
		$(CURDIR)/.coverage \
		$(CURDIR)/backend/.venv \
		$(CURDIR)/backend/.mypy_cache \
		$(CURDIR)/backend/.pytest_cache \
		$(CURDIR)/backend/*.egg-info
	@rm -rf build dist site .uv-cache *.egg-info
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} +

## Basic code checkers
fmt: fmt-go fmt-py ## Format Go and Python sources

fmt-go: ## Run `gofmt` over Go sources
	@gofmt -w $(shell find cli tests -type f -name '*.go' -not -path '*/vendor/*' 2>/dev/null)

fmt-py: venv ## Run `ruff format` over Python sources
	@uv run ruff format $(PYTHON_SRC_DIRS)

lint: lint-go lint-py ## Run Go and Python linters

lint-go: ## Run `golangcli-lint` over Go sources
	@for mod in $(GO_MODULE_DIRS); do \
		cd $(CURDIR)/$$mod && \
		golangci-lint run -E gosec -E iface -E gci ./...; \
	done

lint-py: venv ## Run `ruff check` over Python sources. Pass `FIX=--FIX` to automatically fix the errors
	@uv run ruff check $(PYTHON_SRC_DIRS) $(FIX)

tc: tc-go tc-py ## Run Go and Python code checkers

tc-go: ## Run `mypy` over Python sources
	@for mod in $(GO_MODULE_DIRS); do \
		cd $(CURDIR)/$$mod && $(GO) vet ./...; \
	done

tc-py: venv ## Run `go vet` over Go sources
	@uv run --directory backend mypy .

## Security scans
vc: vc-go vc-py ## Scan Go and Python dependencies for known vulnerabilities

vc-go: ## Run `pip-audit` over Python dependencies
	@for mod in $(GO_MODULE_DIRS); do \
		cd $(CURDIR)/$$mod && $(GO) run golang.org/x/vuln/cmd/govulncheck@latest ./...; \
	done

vc-py: venv ## Run `govulncheck` over Go dependencies
	@uv run --project backend --with pip-audit pip-audit

## Tests
test: test-unit test-contr test-int test-perf ## Run all test suites (unit, contract, integration, performance)

test-py: test-unit-py test-contr-py test-int-py test-perf-py ## Run all test suites for Python code

test-go: test-unit-go test-contr-go test-int-go test-perf-go ## Run all test suites for Go code

test-unit: test-unit-go test-unit-py ## Run unit test suites for Go and Python code

test-unit-go: ## Run unit test suites for Go code
	$(GO) test -v ./tests/go/unit/... 

test-unit-py: venv ## Run unit test suites for Python code
	@PYTHONPATH=$(BE_SRC) uv run --project backend pytest --cov=$(BE_SRC) tests/python/unit

test-contr: test-contr-go test-contr-py ## Run contract test suites for Go and Python code

test-contr-go: ## Run contract test suites for Go code
	@$(GO) test -v ./tests/go/contract/...

test-contr-py: venv ## Run contract test suites for Python code
	@PYTHONPATH=$(BE_SRC) uv run --project backend pytest --cov=$(BE_SRC)/adapters/transport tests/python/contract

test-int: test-int-go test-int-py ## Run integration test suites for Go and Python code

test-int-go: ## Not implemented yet! Run integration test suites for Go code
	@echo "No implemented yet!"

test-int-py: venv ## Run integration test suites for Python code
	@PYTHONPATH=$(BE_SRC) uv run --project backend pytest --cov=$(BE_SRC) tests/python/integration

test-perf: test-perf-go test-perf-py ## Run performance test suites for Go and Python code

test-perf-go: ## Not implemented! Run performance test suites for Go code
	@echo "No implemented yet!"

test-perf-py: venv ## Run performance test suites for Python code
	@PYTHONPATH=$(BE_SRC) uv run --project backend pytest --cov=$(BE_SRC) tests/python/performance

run-be: ## Runs the backend service with local defaults for development testing
	@mkdir -p tmp/ragcli
	@PYTHONPATH=$(BE_SRC) \
		uv run --project backend python -m main \
			--config "$(CURDIR)/docs/install/config/ragcli-config.yaml" \
			--socket "$(CURDIR)/tmp/ragcli/backend.sock" \
			--weaviate-url "http://localhost:8080" \
			--ollama-url "http://localhost:11434" \
			--phoenix-url "http://localhost:6006" \
			--log-level "DEBUG"

## Building & Packaging
pack: pack-go pack-py ## Package Go and Python binaries for installation/development test

pack-go: ## Package Go binaries for installation/development test
	@if [ -f cli/ragman/main.go ]; then \
		$(GO) build -o dist/ragman ./cli/ragman; \
	else \
		echo "Warning: no sources for ragman; skipping build."; \
	fi
	@if [ -f cli/ragadmin/main.go ]; then \
		$(GO) build -o dist/ragadmin ./cli/ragadmin; \
	else \
		echo "Warning: no sources for ragadmin; skipping build."; \
	fi

pack-py: venv ## Package Python binaries for installation/development test
# TODO: fix this
	@uv run --directory $(PY_ROOT) python -m build -o $(CURDIR)/dist

install: install-go install-py ## Install compiled Go and Python binaries
	@echo "Not implemented yet!"

install-go: ## Install compiled Go binaries. Location can be set with `DESTDIR=/usr/local` which is the default.
	@install -d $(DESTDIR)/bin
	@if [ -f dist/ragman ]; then \
		install -m 0755 dist/ragman $(DESTDIR)/bin/ragman; \
	else \
		echo "Warning: ragman binary missing; skipping install."; \
	fi
	@if [ -f dist/ragadmin ]; then \
		install -m 0755 dist/ragadmin $(DESTDIR)/bin/ragadmin; \
	else \
		echo "Warning: ragadmin binary missing; skipping install."; \
	fi

install-py: venv ## Install compiled Python binaries
        
## Documentation
docs: docs-py ## Build project documentation site using `mkdocs`
	@if [ -f "$(MKDOCS_CONFIG)" ]; then \
		ln -sf $(CURDIR)/specs $(CURDIR)/docs; \
		mkdir -p $(MKDOCS_SITE_DIR); \
		uv run mkdocs build --config-file $(MKDOCS_CONFIG) --site-dir $(MKDOCS_SITE_DIR); \
	else \
		echo "Skipping documentation build; $(MKDOCS_CONFIG) not found."; \
	fi

docs-py: venv ## Generate Markdown documentation for Python code.
	@uv run python scripts/docs/generate_backend_docs.py;

docs-serve: ## Serve project documentation locally for preview using `mkdocs`
	@uv run mkdocs serve --config-file $(MKDOCS_CONFIG);
