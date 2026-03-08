#!/usr/bin/env bash
# tests/setup.sh — Set up the test environment for gerrit-review-mcp
#
# Usage:
#   cd gerrit-mcp
#   bash tests/setup.sh
#
# What this script does:
#   1. Verifies system requirements (Python 3.12, uv, Docker)
#   2. Creates .venv/ using uv with Python 3.12
#   3. Installs the package + dev dependencies into .venv/
#   4. Pre-builds the Docker image to populate the layer cache
#   5. Prints run instructions

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
fail() { echo -e "${RED}  ✗ $*${NC}"; exit 1; }
info() { echo -e "  → $*"; }

echo ""
echo "========================================"
echo "  gerrit-review-mcp test environment setup"
echo "========================================"
echo ""

cd "${REPO_ROOT}"

# ── 1. Check Python 3.12 ──────────────────────────────────────────────────────
echo "Checking prerequisites..."

if ! command -v python3.12 &>/dev/null; then
  fail "python3.12 not found. Install with: sudo dnf install -y python3.12 python3.12-pip"
fi
PY_VERSION=$(python3.12 --version 2>&1)
ok "Python: ${PY_VERSION}"

# ── 2. Check uv ───────────────────────────────────────────────────────────────
UV_CMD=""
if command -v uv &>/dev/null; then
  UV_CMD="uv"
elif [ -x "${HOME}/.local/bin/uv" ]; then
  UV_CMD="${HOME}/.local/bin/uv"
else
  fail "uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh\n  Then add ~/.local/bin to your PATH."
fi
UV_VERSION=$(${UV_CMD} --version 2>&1)
ok "uv: ${UV_VERSION}"

# ── 3. Check Docker ───────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  warn "docker not found — Docker integration tests will be skipped"
  DOCKER_AVAILABLE=false
else
  if docker info &>/dev/null 2>&1; then
    ok "Docker daemon: running"
    DOCKER_AVAILABLE=true
  else
    warn "Docker daemon not accessible — check that user is in the 'docker' group"
    warn "Run: sudo usermod -aG docker \$USER && newgrp docker"
    DOCKER_AVAILABLE=false
  fi
fi

echo ""

# ── 4. Create virtual environment ─────────────────────────────────────────────
echo "Creating virtual environment..."
if [ -d ".venv" ]; then
  info ".venv already exists — reinstalling dependencies"
else
  ${UV_CMD} venv .venv --python python3.12
  ok "Created .venv with Python 3.12"
fi

# ── 5. Install package + dev dependencies ─────────────────────────────────────
echo "Installing dependencies..."
${UV_CMD} pip install -e ".[dev]"
ok "Installed gerrit-review-mcp[dev] into .venv"

echo ""

# ── 6. Pre-build Docker image ─────────────────────────────────────────────────
if [ "${DOCKER_AVAILABLE}" = true ]; then
  echo "Pre-building Docker image to warm layer cache..."
  docker build -t gerrit-mcp-test-prebuild . \
    && ok "Docker image 'gerrit-mcp-test-prebuild' built and cached" \
    || warn "Docker image build failed — integration tests may be slow or fail"
else
  warn "Skipping Docker image pre-build (Docker not available)"
fi

echo ""

# ── 7. Summary ────────────────────────────────────────────────────────────────
echo "========================================"
echo -e "${GREEN}  Setup complete!${NC}"
echo "========================================"
echo ""
echo "Run tests:"
echo ""
echo "  # All tests"
echo "  .venv/bin/pytest -v"
echo ""
echo "  # Unit tests only (no Docker)"
echo "  .venv/bin/pytest -v tests/test_auth_config.py tests/test_ssl_config.py \\"
echo "      tests/test_inline_comments.py tests/test_submit_review.py"
echo ""
echo "  # Docker integration tests only"
echo "  .venv/bin/pytest -v tests/test_docker_integration.py"
echo ""
echo "  # Via Makefile"
echo "  make test"
echo ""
