.DEFAULT_GOAL := watchdog
.RECIPEPREFIX := >

UV ?= uv
PYTHON ?= $(UV) run python
PYTEST ?= $(UV) run pytest
BG_LOG_DIR ?= ./logs/current
WATCHDOG_CHECK = $(UV) run python -c "import psutil, sys; sys.exit(0 if any('main.py watchdog' in ' '.join((p.info.get('cmdline') or [])) for p in psutil.process_iter(['cmdline'])) else 1)"

.PHONY: help sync test test-cov trading-engine trading-engine-test cms-server cms-check watchdog \
	trading-engine-bg cms-server-bg watchdog-bg \
	export-minute-history export-minute-daily ingest-minute-history ingest-minute-daily

help:
> @echo "Quant Make Targets"
> @echo ""
> @echo "Default"
> @echo "  make                           # start watchdog"
> @echo ""
> @echo "Dev"
> @echo "  make sync                      # uv sync"
> @echo "  make test                      # uv run pytest"
> @echo "  make test-cov                  # uv run pytest --cov=src --cov-report=term-missing"
> @echo ""
> @echo "Runtime"
> @echo "  make trading-engine            # trading engine"
> @echo "  make trading-engine-bg         # trading engine in background"
> @echo "  make trading-engine-test       # trading engine in test mode"
> @echo "  make cms-server                # CMS HTTP service"
> @echo "  make cms-server-bg             # CMS HTTP service in background"
> @echo "  make cms-check                 # CMS health snapshot"
> @echo "  make watchdog                  # watchdog service"
> @echo "  make watchdog-bg               # watchdog service in background"
> @echo ""
> @echo "Market Data"
> @echo "  make export-minute-history     # export minute history"
> @echo "  make export-minute-daily       # export today's minute history"
> @echo "  make ingest-minute-history     # ingest minute history"
> @echo "  make ingest-minute-daily       # ingest today's minute history"

sync:
> $(UV) sync

test:
> $(PYTEST)

test-cov:
> $(PYTEST) --cov=src --cov-report=term-missing

trading-engine:
> $(PYTHON) main.py run

trading-engine-bg:
> @mkdir -p $(BG_LOG_DIR)
> @nohup $(PYTHON) main.py run >> $(BG_LOG_DIR)/make-run.out 2>&1 < /dev/null & \
> echo $$! > $(BG_LOG_DIR)/run.pid; \
> echo "trading engine started in background, pid=$$(cat $(BG_LOG_DIR)/run.pid)"

trading-engine-test:
> $(PYTHON) main.py test-run

cms-server:
> $(PYTHON) main.py cms-server

cms-server-bg:
> @mkdir -p $(BG_LOG_DIR)
> @nohup $(PYTHON) main.py cms-server >> $(BG_LOG_DIR)/make-cms-server.out 2>&1 < /dev/null & \
> echo $$! > $(BG_LOG_DIR)/cms-server.pid; \
> echo "cms-server started in background, pid=$$(cat $(BG_LOG_DIR)/cms-server.pid)"

cms-check:
> $(PYTHON) main.py cms-check

watchdog:
> @if $(WATCHDOG_CHECK); then \
> echo "watchdog is already running, skip"; \
> else \
> $(PYTHON) main.py watchdog; \
> fi

watchdog-bg:
> @mkdir -p $(BG_LOG_DIR)
> @if $(WATCHDOG_CHECK); then \
> echo "watchdog is already running, skip"; \
> else \
> nohup $(PYTHON) main.py watchdog >> $(BG_LOG_DIR)/make-watchdog.out 2>&1 < /dev/null & \
> echo $$! > $(BG_LOG_DIR)/watchdog.pid; \
> echo "watchdog started in background, pid=$$(cat $(BG_LOG_DIR)/watchdog.pid)"; \
> fi

export-minute-history:
> $(PYTHON) main.py export-minute-history

export-minute-daily:
> $(PYTHON) main.py export-minute-daily

ingest-minute-history:
> $(PYTHON) main.py ingest-minute-history

ingest-minute-daily:
> $(PYTHON) main.py ingest-minute-daily
