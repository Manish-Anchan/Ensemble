# ==============================================================================
# ENSEMBLE: Autonomous Multi-Cast Audio Drama Engine
# Makefile - Common commands and workflows
# ==============================================================================

PYTHON  ?= .venv/bin/python
PYTEST  ?= .venv/bin/pytest
BOOK    ?= samples/the_great_gatsby.pdf
CHAPTER ?= 1
SCENES  ?= 0
START   ?= 1
FORMAT  ?= wav

.PHONY: help test test-v play play-scene produce-ch produce-mp3 produce-all produce-all-mp3 produce-range script-ch script-all cast clean-cache status

# ------------------------------------------------------------------------------
# Default Target: Help Menu
# ------------------------------------------------------------------------------
help:
	@echo "======================================================================"
	@echo "🎭 ENSEMBLE: Drama Engine Command Center"
	@echo "======================================================================"
	@echo "Quick Start Commands:"
	@echo "  make play              Stream Chapter 1 live to speakers (or CHAPTER=X)"
	@echo "  make play-scene        Stream 1 scene for quick verification"
	@echo "  make produce-ch        Produce Chapter 1 audio (WAV, or CHAPTER=X)"
	@echo "  make produce-mp3       Produce Chapter 1 audio in MP3 format"
	@echo "  make produce-all       Produce ALL chapters in batch mode (WAV, resumable)"
	@echo "  make produce-all-mp3   Produce ALL chapters in batch mode in MP3 format"
	@echo "  make produce-range     Produce chapter slice (e.g. START=1 END=3)"
	@echo ""
	@echo "Screenplay & Casting Commands:"
	@echo "  make script-ch         Direct Chapter 1 screenplay (no audio, fast)"
	@echo "  make script-all        Direct all chapters screenplays (no audio)"
	@echo "  make cast              Run Casting Producer to build/update Cast Sheet"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test              Run complete test suite (21 unit tests)"
	@echo "  make test-v            Run test suite with verbose output"
	@echo "  make status            Display outputs summary and generated files"
	@echo "  make clean-cache       Clean __pycache__ and pytest caches"
	@echo "======================================================================"
	@echo "Custom Parameters:"
	@echo "  make play CHAPTER=2 BOOK=samples/other.pdf"
	@echo "  make produce-range START=2 END=4"
	@echo "  make produce-all FORMAT=mp3"
	@echo "======================================================================"

# ------------------------------------------------------------------------------
# Live Streaming Playback (Jitter Buffer -> Speakers)
# ------------------------------------------------------------------------------
play:
	$(PYTHON) -m ensemble.drama $(BOOK) --chapter $(CHAPTER) --play

play-scene:
	$(PYTHON) -m ensemble.drama $(BOOK) --chapter $(CHAPTER) --scenes 1 --play

# ------------------------------------------------------------------------------
# Production & Audio Generation
# ------------------------------------------------------------------------------
produce-ch:
	$(PYTHON) -m ensemble.drama $(BOOK) --chapter $(CHAPTER) --format $(FORMAT)

produce-mp3:
	$(PYTHON) -m ensemble.drama $(BOOK) --chapter $(CHAPTER) --mp3

produce-all:
	$(PYTHON) -m ensemble.drama $(BOOK) --all --format $(FORMAT)

produce-all-mp3:
	$(PYTHON) -m ensemble.drama $(BOOK) --all --mp3

produce-range:
	$(PYTHON) -m ensemble.drama $(BOOK) --all --start-chapter $(START) --end-chapter $(END)

produce-force:
	$(PYTHON) -m ensemble.drama $(BOOK) --all --force

# ------------------------------------------------------------------------------
# Screenplay Directing (Script Only, No Audio)
# ------------------------------------------------------------------------------
script-ch:
	$(PYTHON) -m ensemble.drama $(BOOK) --chapter $(CHAPTER) --script-only

script-all:
	$(PYTHON) -m ensemble.drama $(BOOK) --all --script-only

# ------------------------------------------------------------------------------
# Casting Producer
# ------------------------------------------------------------------------------
cast:
	$(PYTHON) -m ensemble.producer $(BOOK)

# ------------------------------------------------------------------------------
# Testing & Verification
# ------------------------------------------------------------------------------
test:
	$(PYTEST)

test-v:
	$(PYTEST) -v

# ------------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------------
status:
	@echo "📁 Outputs Directory Status:"
	@ls -lh outputs/ 2>/dev/null || echo "No outputs directory yet."
	@echo ""
	@echo "📋 Cast Sheets:"
	@ls -lh samples/*_cast.json 2>/dev/null || true
	@ls -lh outputs/*/*cast*.json 2>/dev/null || true

clean-cache:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Cache cleaned."

clean-outputs:
	rm -rf outputs/*
	@echo "✓ Cleaned all generated outputs in outputs/."
