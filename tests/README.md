# Test Environment Setup

This document describes all system requirements and setup steps needed to run the full test suite for `gerrit-review-mcp`.

---

## Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12 | `python3.12` must be on PATH |
| uv | any | Fast Python package manager — used for venv creation |
| Docker | 20.10+ | Required for Docker integration tests |
| Docker socket | `/var/run/docker.sock` | Current user must be in `docker` group |

---

## Quick Setup

Run the provided setup script from the repo root:

```bash
cd gerrit-mcp
bash tests/setup.sh
```

This will:
1. Verify system requirements (Python 3.12, uv, Docker)
2. Create `.venv/` using `uv` with Python 3.12
3. Install the package and all dev dependencies into `.venv/`
4. Pre-build the Docker image for integration tests (populates Docker layer cache)
5. Print a summary and run instructions

---

## Manual Setup

If you prefer to set up manually:

```bash
# 1. Create virtual environment with Python 3.12
uv venv .venv --python python3.12

# 2. Install package + dev dependencies
uv pip install -e ".[dev]"

# 3. Pre-build Docker image (speeds up first test run)
docker build -t gerrit-mcp-test-prebuild .
```

---

## Running Tests

```bash
# All tests (unit + Docker integration)
.venv/bin/pytest -v

# Unit tests only (no Docker required)
.venv/bin/pytest -v tests/test_auth_config.py tests/test_ssl_config.py \
    tests/test_inline_comments.py tests/test_submit_review.py

# Docker integration tests only
.venv/bin/pytest -v tests/test_docker_integration.py

# Via Makefile (after setup)
make test
```

> **Note:** The Docker integration tests build a fresh image on each run (~30s on first run, faster with cached layers). Allow at least 120 seconds for the full suite.

---

## System Notes

### Python 3.12 via `python3.12`

The project requires Python 3.10+ and targets 3.12 for RPM builds. On RHEL/Rocky 9:

```bash
sudo dnf install -y python3.12 python3.12-pip
```

### uv

`uv` must be on PATH. Install for the current user:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Or: pip install uv
```

After install, ensure `~/.local/bin` is in your PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Docker group membership

The user running tests must be in the `docker` group:

```bash
sudo usermod -aG docker $USER
# Log out and back in, or run: newgrp docker
```

Verify:
```bash
docker info >/dev/null 2>&1 && echo "Docker OK"
```

### Docker build context

A [`.dockerignore`](../.dockerignore) file excludes `.venv/`, `rpm/`, `__pycache__/` etc. from the Docker build context. Without it, the context transfer is slow and test collection hangs.

---

## Environment Variables for Tests

The Docker integration tests create a temporary `.env` file automatically with stub values. For unit tests, no real Gerrit credentials are needed.

| Variable | Used in | Required |
|----------|---------|----------|
| `TEST_STARTUP_TIMEOUT` | `test_docker_integration.py` | No (default: 30s) |
| `TEST_LOGS_SETTLE_DELAY` | `test_docker_integration.py` | No (default: 2.0s) |
| `TEST_CONTAINER_READY_TIMEOUT` | `test_docker_integration.py` | No (default: 10s) |
| `DOCKER_HOST` | `test_docker_integration.py` | No (uses socket default) |

---

## CI/CD

For CI/CD environments (e.g. Jenkins with Docker-in-Docker):

```bash
# Ensure Docker socket is mounted or DOCKER_HOST is set
# Run full suite
.venv/bin/pytest -v
```

Set longer timeouts if needed:
```bash
TEST_STARTUP_TIMEOUT=60 TEST_LOGS_SETTLE_DELAY=3 .venv/bin/pytest -v
```
