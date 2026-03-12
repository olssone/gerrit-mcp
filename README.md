# Gerrit Review MCP Server

MCP server for Gerrit Code Review integration

Provides tools for fetching changes, comparing patchsets, submitting reviews, and posting draft inline comments via the Gerrit REST API.

---

## Repository Structure

```
gerrit-mcp/
├── src/                           # Python package
│   ├── __init__.py
│   ├── config.py                  # Auth configuration module
│   └── server.py                  # MCP server (entry point: main())
├── tests/
│   ├── conftest.py                # pytest path setup
│   ├── test_auth_config.py
│   ├── test_docker_integration.py
│   ├── test_draft_comments.py     # Draft comments feature tests (100% coverage)
│   ├── test_inline_comments.py
│   ├── test_ssl_config.py
│   └── test_submit_review.py
├── rpm/
│   ├── SOURCES/                   # Tarballs (generated, gitignored)
│   └── SPECS/
│       └── gerrit-review-mcp.spec # RPM spec
├── Dockerfile                     # Container image (python:3.12-slim)
├── Makefile                       # RPM + dev targets
├── pyproject.toml                 # Project metadata + build config
├── requirements.txt               # Pinned runtime deps
└── README.md
```

---

## Features

### Fetch Change Details
```python
fetch_gerrit_change(change_id: str, patchset_number: Optional[str] = None, include_comments: bool = False)
```
- Fetches complete change information including files and patch sets
- Returns diffs, author/reviewer details, comments, and review history
- Optional inline comment retrieval via `include_comments=True`
- Supports file exclusion via `GERRIT_EXCLUDED_PATTERNS`

### Compare Patchset Differences
```python
fetch_patchset_diff(change_id: str, base_patchset: str, target_patchset: str, file_path: Optional[str] = None)
```
- Compare differences between two patchsets of a change
- View specific file differences or all changed files

### Submit Review Feedback
```python
submit_gerrit_review(
    change_id: str,
    message: Optional[str] = None,
    patchset_number: Optional[str] = None,
    labels: Optional[Dict[str, int]] = None,
    comments: Optional[List[Dict[str, Any]]] = None,
    notify: str = "OWNER",
)
```
- Post summary feedback, vote labels (e.g., `{"Code-Review": 1}`), and inline comments
- Control notification scope: `NONE`, `OWNER`, `OWNER_REVIEWERS`, `ALL`

### Post Draft Comments

Draft comments are **visible only to you** until published via the Gerrit UI.
Post them with the AI, then audit and publish in Gerrit as usual.

```python
# Post a single draft comment
create_draft_comment(
    change_id: str,
    path: str,
    message: str,
    patchset_number: Optional[str] = None,
    line: Optional[int] = None,
    side: Optional[str] = None,          # "REVISION" (default) or "PARENT"
    range: Optional[Dict[str, int]] = None,
    in_reply_to: Optional[str] = None,
    unresolved: Optional[bool] = None,
)

# Post multiple draft comments in batch (partial-success model)
create_draft_comments(
    change_id: str,
    comments: List[Dict[str, Any]],      # list of comment dicts
    patchset_number: Optional[str] = None,
)
```

Each comment dict passed to `create_draft_comments()` supports:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | str | ✅ | File path, e.g. `"src/foo.cpp"` |
| `message` | str | ✅ | Comment text |
| `line` | int | — | Line number (positive integer) |
| `side` | str | — | `"REVISION"` or `"PARENT"` |
| `range` | dict | — | `{start_line, start_character, end_line, end_character}` |
| `in_reply_to` | str | — | ID of a comment to reply to |
| `unresolved` | bool | — | Mark as unresolved thread |

### Example Usage

```python
# Fetch latest patchset
change = fetch_gerrit_change("23824")

# Post draft comments (visible only to you; review and publish in Gerrit UI)
batch = create_draft_comments(
    change_id="23824",
    comments=[
        {"path": "src/app.py", "line": 42, "message": "Consider using a context manager here."},
        {"path": "src/app.py", "line": 78, "message": "This variable shadows the outer scope."},
        {"path": "tests/test_app.py", "line": 12, "message": "Missing edge case: empty input."},
    ],
    patchset_number="3",
)
print(f"Posted {batch['succeeded']}/{batch['total']} drafts")

# --- Standard (immediate) review ---

# Submit a vote with an inline comment (immediately visible)
submit_gerrit_review(
    change_id="23824",
    message="Looks good overall",
    labels={"Code-Review": 1},
    comments=[{"path": "src/app.py", "line": 42, "message": "Nice refactor."}],
    patchset_number="2",
    notify="OWNER_REVIEWERS",
)

# Compare two patchsets
diff = fetch_patchset_diff("23824", "1", "2")

# Get diff for a specific file
file_diff = fetch_patchset_diff("23824", "1", "2", "path/to/file.py")
```

---

## Prerequisites

- Python 3.10 or higher (Python 3.12 recommended)
- Gerrit HTTP access credentials (HTTP password from Gerrit Settings > HTTP Credentials)

---

## Installation

### Option 1: Development (editable install)

```bash
git clone https://github.com/olssone/gerrit-mcp.git
cd gerrit-mcp

python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
make dev-install
# or: pip install -e ".[dev]"
```

### Option 2: System-wide via RPM (RHEL/Rocky Linux 9)

```bash
# Build requirements
sudo dnf install -y rpm-build python3.12 python3.12-pip

# Build and install
make rpm
make install
```

See the [RPM Build System](#rpm-build-system) section for full details.

### Option 3: Docker

```bash
docker build -t gerrit-review-mcp .
docker run --env-file .env gerrit-review-mcp
```

---

## Configuration

Set environment variables or create a `.env` file in the project root:

```bash
# Required
GERRIT_HOST=gerrit.example.com          # Hostname only — no https://
GERRIT_USER=your-username
GERRIT_HTTP_PASSWORD=your-http-password  # From Gerrit Settings > HTTP Credentials

# Optional
GERRIT_AUTH_METHOD=digest               # 'digest' (default) or 'basic' (LDAP)
GERRIT_PASSWORD=your-ldap-password      # Required only when GERRIT_AUTH_METHOD=basic
GERRIT_EXCLUDED_PATTERNS=\.pbxproj$,\.xcworkspace$,node_modules/  # Comma-separated regex

# TLS (optional)
GERRIT_SSL_VERIFY=true                  # Set to 'false' to skip verification
GERRIT_CA_BUNDLE=/path/to/ca.pem        # Custom CA bundle (takes precedence over SSL_VERIFY)
```

### Authentication Methods

| Method | Env var for password | Use case |
|--------|---------------------|----------|
| `digest` (default) | `GERRIT_HTTP_PASSWORD` | Standard Gerrit HTTP credentials |
| `basic` | `GERRIT_PASSWORD` | LDAP / `gitBasicAuthPolicy = HTTP_LDAP` |

---

## MCP Client Configuration

### After RPM install (system-wide)

```json
{
  "mcpServers": {
    "gerrit-review-mcp": {
      "command": "gerrit-review-mcp",
      "args": [],
      "env": {
        "GERRIT_HOST": "gerrit.example.com",
        "GERRIT_USER": "your-username",
        "GERRIT_HTTP_PASSWORD": "your-http-password"
      },
      "alwaysAllow": [
        "fetch_gerrit_change",
        "fetch_patchset_diff",
        "submit_gerrit_review",
        "create_draft_comment",
        "create_draft_comments"
      ]
    }
  }
}
```

### After development install (venv)

```json
{
  "mcpServers": {
    "gerrit-review-mcp": {
      "command": "/path/to/gerrit-mcp/.venv/bin/gerrit-review-mcp",
      "args": [],
      "env": {
        "GERRIT_HOST": "gerrit.example.com",
        "GERRIT_USER": "your-username",
        "GERRIT_HTTP_PASSWORD": "your-http-password"
      },
      "alwaysAllow": [
        "fetch_gerrit_change",
        "fetch_patchset_diff",
        "submit_gerrit_review",
        "create_draft_comment",
        "create_draft_comments"
      ]
    }
  }
}
```

---

## Development

### Make Targets

| Target        | Description                                  |
|---------------|----------------------------------------------|
| `dev-install` | Install package + dev deps in editable mode  |
| `test`        | Run pytest suite                             |
| `lint`        | Check formatting with black + isort          |
| `format`      | Auto-format with black + isort               |
| `rpm`         | Build binary RPM                             |
| `srpm`        | Build source RPM                             |
| `tarball`     | Create source tarball only                   |
| `install`     | Install the RPM locally via dnf              |
| `clean`       | Remove RPM build artifacts                   |
| `info`        | Show build configuration                     |
| `help`        | Show help                                    |

### Running Tests

```bash
# Install dev deps
make dev-install

# Run all tests
make test

# Run only unit tests (no Docker required)
pytest -m "not docker"

# Run with coverage
pytest --cov=src --cov-report=html

# Run integration/Docker tests
pytest -m docker
```

### Test Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TEST_STARTUP_TIMEOUT` | `30` | Container startup timeout (seconds) |
| `TEST_LOGS_SETTLE_DELAY` | `0` | Delay before checking logs (seconds) |
| `DOCKER_HOST` | — | Remote Docker daemon host |

Docker integration tests are automatically skipped if Docker is not available.

---

## Troubleshooting

**Authentication failed:**
- Verify `GERRIT_HTTP_PASSWORD` is set and correct
- Check `GERRIT_HOST` is hostname only (no `https://`)
- Test with curl: `curl -u "user:pass" https://gerrit.example.com/a/changes/?q=status:open`

**`GERRIT_AUTH_METHOD=basic` not working:**
- Verify Gerrit config has `gitBasicAuthPolicy = HTTP` or `HTTP_LDAP`
- Set `GERRIT_PASSWORD` (not `GERRIT_HTTP_PASSWORD`) for LDAP

**Self-signed certificate errors:**
- Set `GERRIT_SSL_VERIFY=false` (temporary workaround)
- Or provide `GERRIT_CA_BUNDLE=/path/to/ca.pem` for a custom CA

---

## RPM Build System

### Quick Start

```bash
sudo dnf install -y rpm-build python3.12 python3.12-pip
make rpm
make install
```

### Build Output

- Binary RPM: `rpm/RPMS/x86_64/gerrit-review-mcp-<version>-1.el9.x86_64.rpm`
- Source tarball: `rpm/SOURCES/gerrit-review-mcp-<version>.tar.gz`

### Installed Files

```
/opt/gerrit-review-mcp/
├── venv/                          # Python 3.12 virtual environment
│   └── bin/
│       └── gerrit-review-mcp      # Installed console script (entry point)
├── bin/
│   └── gerrit-review-mcp          # Wrapper → venv/bin/gerrit-review-mcp
└── share/examples/
    └── mcp-config.json            # Example MCP client configuration

/usr/bin/gerrit-review-mcp -> /opt/gerrit-review-mcp/bin/gerrit-review-mcp
```

### Version Management

Version is read automatically from `pyproject.toml`. Override at build time:

```bash
make rpm VERSION=0.2.0 RELEASE=2
```

### Uninstall

```bash
sudo dnf remove gerrit-review-mcp
```

---

## Example Use Case: LLM-Assisted Code Review

One practical way to use the Gerrit MCP server is to integrate it with an LLM
agent to perform an automated first-pass code inspection. The MCP server acts
as a structured integration layer between Gerrit and automated reasoning
systems — the MCP server provides infrastructure primitives, the LLM provides
analysis, and the human reviewer retains accountability.

### 1. Retrieve Change Context

Use [`fetch_gerrit_change`](#fetch-change-details) and
[`fetch_patchset_diff`](#compare-patchset-differences) to retrieve:

- Change metadata and commit message
- Target branch information
- The list of modified files
- Line-level diffs for the patchset

This provides the LLM with the authoritative description and delta surface of
the change.

### 2. Perform Repository-Aware Analysis

After retrieving the patchset diff, the LLM can:

- Check out the repository at the patchset revision
- Traverse related files not included in the diff
- Inspect call sites of modified interfaces
- Analyze consumers of changed data structures
- Evaluate architectural and dependency impact

This enables reasoning beyond the patchset itself, covering areas such as:

- Control and data flow implications
- API contract changes
- Error handling completeness
- Concurrency risks
- Performance impact
- Security implications
- Backward compatibility

The MCP server provides the change context; the LLM performs the reasoning.

### 3. Generate Structured Findings

Instruct the LLM to categorize findings into:

| Category | Description |
|----------|-------------|
| **Defects** | Correctness or safety issues |
| **Concerns** | Design or maintainability risks |
| **Questions** | Clarifications for the author |

Each finding should reference a file path and, when applicable, a line number.

### 4. Post Draft Comments Back to Gerrit

Using [`create_draft_comment`](#post-draft-comments) or
[`create_draft_comments`](#post-draft-comments), the LLM posts its findings as
draft comments directly on the Gerrit change.

Importantly, **the agent does not submit or vote on the review** — it only
creates draft comments. The drafts are visible only to the reviewer until
explicitly published.

```python
create_draft_comments(
    change_id="31357",
    comments=[
        {
            "path": "src/component.cpp",
            "line": 142,
            "message": "Defect: resource acquired here is not released on the error path at line 158.",
            "unresolved": True,
        },
        {
            "path": "src/component.cpp",
            "line": 87,
            "message": "Concern: this interface change may break callers in src/adapter.cpp (line 203).",
            "unresolved": True,
        },
        {
            "path": "include/protocol.h",
            "line": 34,
            "message": "Question: is the new field intended to be zero-initialized for legacy clients?",
            "unresolved": True,
        },
    ],
)
```

### 5. Human Disposition

A human reviewer then:

1. Reviews the generated draft comments in Gerrit
2. Edits or removes comments as appropriate
3. Adds additional judgment where necessary
4. Submits the finalized review

### Why This Matters

This model augments existing review workflows without altering Gerrit's core
review model:

- **MCP server** — reliable access to change metadata, diffs, and comment
  creation APIs
- **LLM** — higher-level inspection logic and structured finding generation
- **Human reviewer** — final accountability and editorial control

---

## License

MIT
