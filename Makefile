# Makefile for Gerrit Review MCP Server
#
# RPM packaging:
#   make rpm          - Build binary RPM
#   make srpm         - Build source RPM
#   make tarball      - Create source tarball
#   make install      - Install the RPM
#   make test-install - Verify the installed RPM package
#   make clean        - Clean build artifacts
#
# Development:
#   make dev-install  - Create .venv and install package + dev deps
#   make test         - Run pytest suite via .venv
#   make lint         - Run black + isort checks via .venv
#   make format       - Auto-format with black + isort via .venv
#
#   make help         - Show this help

.PHONY: all clean srpm rpm install test-install test lint format dev-install help info tarball

# Configuration
NAME    := gerrit-review-mcp
# Extract version from pyproject.toml, fallback to 0.1.0 if not found
VERSION := $(shell grep '^version' pyproject.toml 2>/dev/null | sed 's/.*= *"\(.*\)"/\1/' || echo "0.1.0")
RELEASE := 1

# The source IS this repository root
SOURCE_DIR     := $(CURDIR)
RPM_DIR        := $(CURDIR)/rpm
SPEC_FILE      := $(RPM_DIR)/SPECS/$(NAME).spec
SOURCE_TARBALL := $(RPM_DIR)/SOURCES/$(NAME)-$(VERSION).tar.gz

# Virtual environment toolchain
VENV    := $(CURDIR)/.venv
PYTHON  := $(VENV)/bin/python3
PYTEST  := $(VENV)/bin/pytest
BLACK   := $(VENV)/bin/black
ISORT   := $(VENV)/bin/isort
UV      := $(shell command -v uv 2>/dev/null || echo "$(HOME)/.local/bin/uv")

# Default target
all: rpm

help:
	@echo "Gerrit Review MCP Server"
	@echo ""
	@echo "RPM targets:"
	@echo "  all          - Build binary RPM (default)"
	@echo "  srpm         - Build source RPM"
	@echo "  tarball      - Create source tarball"
	@echo "  rpm          - Build binary RPM"
	@echo "  install      - Install the RPM locally via dnf"
	@echo "  test-install - Verify the installed RPM package"
	@echo "  clean        - Clean RPM build artifacts"
	@echo ""
	@echo "Dev targets:"
	@echo "  dev-install  - Create .venv and install package + dev deps"
	@echo "  test         - Run pytest suite (uses .venv)"
	@echo "  lint         - Check formatting with black + isort (uses .venv)"
	@echo "  format       - Auto-format with black + isort (uses .venv)"
	@echo ""
	@echo "Configuration:"
	@echo "  NAME:    $(NAME)"
	@echo "  VERSION: $(VERSION)"
	@echo "  RELEASE: $(RELEASE)"
	@echo "  SOURCE:  $(SOURCE_DIR)"
	@echo "  VENV:    $(VENV)"
	@echo ""

# ── Dev targets ───────────────────────────────────────────────────────────────

# Create .venv and install package + dev dependencies
dev-install:
	@echo "Setting up development environment..."
	@if [ -x "$(UV)" ]; then \
	  echo "Using uv..."; \
	  $(UV) venv $(VENV) --python python3.12; \
	  $(UV) pip install -e ".[dev]"; \
	else \
	  echo "uv not found, falling back to python3.12 venv + pip..."; \
	  python3.12 -m venv $(VENV); \
	  $(PYTHON) -m pip install -e ".[dev]"; \
	fi
	@echo ""
	@echo "Dev environment ready. Run tests with: make test"

# Run pytest suite
test: $(PYTEST)
	$(PYTEST) -v

# Check code formatting (non-destructive)
lint: $(BLACK) $(ISORT)
	$(BLACK) --check src/ tests/
	$(ISORT) --check-only src/ tests/

# Auto-format with black and isort
format: $(BLACK) $(ISORT)
	$(BLACK) src/ tests/
	$(ISORT) src/ tests/

# Ensure .venv tools exist; prompt to run dev-install if missing
$(PYTEST) $(BLACK) $(ISORT):
	@echo "ERROR: .venv not set up. Run: make dev-install"
	@exit 1

# ── RPM targets ───────────────────────────────────────────────────────────────

# Create source tarball from this repository
tarball:
	@echo "Creating source tarball: $(SOURCE_TARBALL)"
	@mkdir -p $(RPM_DIR)/SOURCES
	@cd $(SOURCE_DIR) && \
	  tar --exclude='.git' \
	      --exclude='.venv' \
	      --exclude='__pycache__' \
	      --exclude='*.pyc' \
	      --exclude='*.pyo' \
	      --exclude='.pytest_cache' \
	      --exclude='*.egg-info' \
	      --exclude='rpm/BUILD' \
	      --exclude='rpm/BUILDROOT' \
	      --exclude='rpm/RPMS' \
	      --exclude='rpm/SRPMS' \
	      --exclude='rpm/SOURCES/*.tar.gz' \
	      --exclude='.gitignore' \
	      --exclude='.env*' \
	      --transform "s,^\.,$(NAME)-$(VERSION)," \
	      -czf $(SOURCE_TARBALL) \
	      .
	@echo "Source tarball created: $(SOURCE_TARBALL)"
	@ls -lh $(SOURCE_TARBALL)

# Build source RPM
srpm: tarball
	@echo "Building source RPM..."
	@rpmbuild -bs \
	  --define "_topdir $(RPM_DIR)" \
	  --define "version $(VERSION)" \
	  --define "release $(RELEASE)" \
	  $(SPEC_FILE)
	@echo "Source RPM built successfully:"
	@ls -lh $(RPM_DIR)/SRPMS/$(NAME)-$(VERSION)-$(RELEASE).*.src.rpm

# Build binary RPM
rpm: tarball
	@echo "Building binary RPM..."
	@rpmbuild -bb \
	  --define "_topdir $(RPM_DIR)" \
	  --define "version $(VERSION)" \
	  --define "release $(RELEASE)" \
	  $(SPEC_FILE)
	@echo ""
	@echo "=========================================="
	@echo "Binary RPM built successfully!"
	@echo "=========================================="
	@ls -lh $(RPM_DIR)/RPMS/x86_64/$(NAME)-$(VERSION)-$(RELEASE).*.rpm
	@echo ""
	@echo "To install:"
	@echo "  sudo dnf install $(RPM_DIR)/RPMS/x86_64/$(NAME)-$(VERSION)-$(RELEASE).*.rpm"
	@echo ""
	@echo "Or use:"
	@echo "  make install"

# Install the RPM locally
install:
	@echo "Checking for RPM package..."
	@if ! ls $(RPM_DIR)/RPMS/x86_64/$(NAME)-$(VERSION)-$(RELEASE).*.rpm 1>/dev/null 2>&1; then \
	  echo "ERROR: RPM not found. Build it first with 'make rpm'"; \
	  exit 1; \
	fi
	@echo "Checking if already installed..."
	@if rpm -q $(NAME) >/dev/null 2>&1; then \
	  echo "Package $(NAME) is already installed."; \
	  echo "To upgrade: sudo dnf upgrade $(RPM_DIR)/RPMS/x86_64/$(NAME)-$(VERSION)-$(RELEASE).*.rpm"; \
	  echo "To reinstall, first remove: sudo dnf remove $(NAME)"; \
	  exit 1; \
	fi
	@echo "Installing RPM..."
	@sudo dnf install -y $(RPM_DIR)/RPMS/x86_64/$(NAME)-$(VERSION)-$(RELEASE).*.rpm
	@echo ""
	@echo "Installation complete! Test with: make test-install"

# Verify the installed RPM package
test-install:
	@echo "Testing RPM installation..."
	@echo ""
	@echo "1. Checking command availability..."
	@which $(NAME) || (echo "ERROR: Command not found in PATH" && exit 1)
	@echo "   ✓ Command found: $$(which $(NAME))"
	@echo ""
	@echo "2. Checking installation directory..."
	@test -d /opt/$(NAME) || (echo "ERROR: Installation directory not found" && exit 1)
	@echo "   ✓ Installation directory exists: /opt/$(NAME)"
	@echo ""
	@echo "3. Checking virtual environment..."
	@test -f /opt/$(NAME)/venv/bin/python3 || (echo "ERROR: Virtual environment not found" && exit 1)
	@echo "   ✓ Virtual environment found"
	@echo ""
	@echo "=========================================="
	@echo "All tests passed!"
	@echo "=========================================="
	@echo ""
	@echo "Example MCP configuration:"
	@cat /opt/$(NAME)/share/examples/mcp-config.json

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	@rm -rf $(RPM_DIR)/BUILD/*
	@rm -rf $(RPM_DIR)/BUILDROOT/*
	@rm -f  $(RPM_DIR)/RPMS/x86_64/$(NAME)-*.rpm
	@rm -f  $(RPM_DIR)/SRPMS/$(NAME)-*.rpm
	@rm -f  $(RPM_DIR)/SOURCES/$(NAME)-*.tar.gz
	@echo "Clean complete."

# Show current configuration
info:
	@echo "Build Configuration:"
	@echo "  Package Name:    $(NAME)"
	@echo "  Version:         $(VERSION)"
	@echo "  Release:         $(RELEASE)"
	@echo "  Source Dir:      $(SOURCE_DIR)"
	@echo "  RPM Dir:         $(RPM_DIR)"
	@echo "  Spec File:       $(SPEC_FILE)"
	@echo "  Source Tarball:  $(SOURCE_TARBALL)"
	@echo "  Venv:            $(VENV)"
	@echo ""
	@echo "Build Requirements:"
	@echo "  - python3.12"
	@echo "  - python3.12-pip"
	@echo "  - rpmbuild"
