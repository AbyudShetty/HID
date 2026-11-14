# Targets from plan §18.1. On machines without `make` (this Windows laptop) use:  python tasks.py <target>
PY ?= $(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,$(if $(wildcard .venv/bin/python),.venv/bin/python,python))

.PHONY: test test-models test-integration lint bench up down kiosk-test

test:
	$(PY) -m pytest backend/tests -m "not models and not integration" -q

test-models:
	$(PY) -m pytest backend/tests -m models -q

test-integration:
	$(PY) -m pytest backend/tests -m integration -q

kiosk-test:
	cd kiosk && npm test

lint:
	$(PY) -m ruff check backend eval tools experiments

bench:
	$(PY) tools/bench_e2e.py

up:
	docker compose up --build -d

down:
	docker compose down
