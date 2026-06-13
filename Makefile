# Makefile for Research Synthesis & Contradiction Engine

ifeq ($(OS),Windows_NT)
    VENV_BIN = .venv/Scripts
    PYTHON = $(VENV_BIN)/python.exe
    PIP = $(VENV_BIN)/pip.exe
    RUFF = $(VENV_BIN)/ruff.exe
    PYTEST = $(VENV_BIN)/pytest.exe
else
    VENV_BIN = .venv/bin
    PYTHON = $(VENV_BIN)/python
    PIP = $(VENV_BIN)/pip
    RUFF = $(VENV_BIN)/ruff
    PYTEST = $(VENV_BIN)/pytest
endif

# LIMIT=0 means full dataset. Override for quick iteration: make eval-scifact LIMIT=60
LIMIT ?= 0

.PHONY: install run test eval-scifact eval-scifact-fast lint clean

install:
	python -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

run:
	$(PYTHON) -m src.main "$(QUERY)"

test:
	$(PYTEST) tests/ -v

eval-scifact:
	$(PYTHON) -m evaluation.scifact_eval --limit $(LIMIT)

# Quick 60-pair smoke test for development iteration (~30 sec on CPU)
eval-scifact-fast:
	$(PYTHON) -m evaluation.scifact_eval --limit 60

lint:
	$(RUFF) check src/ tests/

clean:
	@ifeq ($(OS),Windows_NT) \
		if exist .venv rmdir /s /q .venv; \
		if exist *.egg-info rmdir /s /q *.egg-info; \
	else \
		rm -rf .venv build dist *.egg-info; \
	endif
