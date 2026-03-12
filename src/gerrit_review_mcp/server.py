import json
import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import Context, FastMCP

try:
    from .config import create_auth_handler, get_password
except ImportError:
    from config import create_auth_handler, get_password  # type: ignore[no-redef]

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT = 30

# Valid Gerrit comment side values for draft comments
VALID_DRAFT_SIDES = {"REVISION", "PARENT"}

# Load environment variables
load_dotenv()


@dataclass
class GerritContext:
    host: str
    user: str
    http_password: Optional[str] = None
    verify_ssl: Union[bool, str] = True


def resolve_ssl_verification_setting() -> Union[bool, str]:
    """Resolve SSL verification behaviour based on environment configuration."""
    ssl_verify_env = os.getenv("GERRIT_SSL_VERIFY")
    ca_bundle_env = os.getenv("GERRIT_CA_BUNDLE")

    if ca_bundle_env:
        ca_bundle_clean = ca_bundle_env.strip()
        if not ca_bundle_clean:
            raise ValueError(
                "GERRIT_CA_BUNDLE is set but empty after trimming whitespace. "
                "Please provide a valid certificate bundle path or unset the variable."
            )
        ca_path = Path(ca_bundle_clean).expanduser()
        if not (ca_path.exists() and ca_path.is_file()):
            raise ValueError(
                f"Configured GERRIT_CA_BUNDLE path '{ca_path}' does not exist. "
                "Please provide a valid certificate bundle path or unset the variable."
            )
        return str(ca_path)

    if ssl_verify_env is None:
        return True

    normalized_value = ssl_verify_env.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        logger.warning(
            "TLS verification disabled via GERRIT_SSL_VERIFY. Use with caution."
        )
        return False

    potential_path = Path(ssl_verify_env.strip()).expanduser()
    if potential_path.exists() and potential_path.is_file():
        return str(potential_path)

    raise ValueError(
        "Invalid GERRIT_SSL_VERIFY value. Provide true/false or a path to a CA bundle."
    )


def build_review_comments(
    comments: Optional[List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Convert a flat comment definition list into Gerrit's review payload structure."""
    if not comments:
        return {}

    comment_map: Dict[str, List[Dict[str, Any]]] = {}

    for index, comment in enumerate(comments, start=1):
        if not isinstance(comment, dict):
            raise ValueError(
                f"Comment entry #{index} must be a mapping with 'path' and 'message' keys."
            )

        path = comment.get("path")
        message = comment.get("message")

        if not path or not isinstance(path, str):
            raise ValueError(f"Comment entry #{index} is missing a valid 'path' value.")
        if not message or not isinstance(message, str):
            raise ValueError(f"Comment entry #{index} is missing a valid 'message'.")

        payload_comment = {
            k: v for k, v in comment.items() if k != "path" and v is not None
        }
        line_value = payload_comment.get("line")
        if line_value is not None and (
            not isinstance(line_value, int) or line_value <= 0
        ):
            raise ValueError(
                f"Comment entry #{index} has invalid 'line' value; must be a positive integer."
            )
        range_value = payload_comment.get("range")
        if range_value is not None and not isinstance(range_value, dict):
            raise ValueError(
                f"Comment entry #{index} has invalid 'range' value; must be a mapping."
            )
        payload_comment.setdefault("message", message)

        comment_map.setdefault(path, []).append(payload_comment)

    return comment_map


def build_draft_comment_payload(
    comment: Dict[str, Any],
    index: int = 1,
) -> Dict[str, Any]:
    """Validate and normalise a single draft comment dict into a Gerrit PUT body.

    Args:
      comment: Mapping with at least 'path' and 'message' keys.
      index: 1-based position in a batch (used in error messages).

    Returns:
      Dict ready to send as the JSON body of PUT .../drafts.

    Raises:
      ValueError: If any required or typed field is invalid.
    """
    if not isinstance(comment, dict):
        raise ValueError(
            f"Draft comment entry #{index} must be a mapping with 'path' and 'message' keys."
        )

    path = comment.get("path")
    message = comment.get("message")

    if not path or not isinstance(path, str):
        raise ValueError(
            f"Draft comment entry #{index} is missing a valid 'path' value."
        )
    if not message or not isinstance(message, str):
        raise ValueError(
            f"Draft comment entry #{index} is missing a valid 'message' value."
        )

    line_value = comment.get("line")
    if line_value is not None:
        if not isinstance(line_value, int) or isinstance(line_value, bool) or line_value <= 0:
            raise ValueError(
                f"Draft comment entry #{index} has invalid 'line' value; "
                "must be a positive integer."
            )

    side_value = comment.get("side")
    if side_value is not None and side_value not in VALID_DRAFT_SIDES:
        raise ValueError(
            f"Draft comment entry #{index} has invalid 'side' value '{side_value}'; "
            f"must be one of {sorted(VALID_DRAFT_SIDES)}."
        )

    range_value = comment.get("range")
    if range_value is not None and not isinstance(range_value, dict):
        raise ValueError(
            f"Draft comment entry #{index} has invalid 'range' value; must be a mapping."
        )

    # Build payload, stripping None values
    payload: Dict[str, Any] = {"path": path, "message": message}
    for key in ("line", "side", "range", "in_reply_to", "unresolved"):
        val = comment.get(key)
        if val is not None:
            payload[key] = val

    return payload


def _resolve_revision(
    ctx: Context,
    change_id: str,
    patchset_number: Optional[str],
) -> str:
    """Resolve a patchset number (or None) to a revision hash.

    Args:
      ctx: MCP request context carrying GerritContext.
      change_id: Gerrit change identifier.
      patchset_number: Optional patchset number string; None uses current revision.

    Returns:
      Revision SHA string.

    Raises:
      ValueError: If the requested patchset is not found, or no current revision.
    """
    change_endpoint = f"a/changes/{change_id}/detail?o=ALL_REVISIONS"
    change_info = make_gerrit_rest_request(ctx, change_endpoint)

    revisions = change_info.get("revisions", {})
    current_revision = change_info.get("current_revision")

    if patchset_number:
        for rev_hash, info in revisions.items():
            if str(info.get("_number")) == str(patchset_number):
                return rev_hash
        available = sorted(str(info.get("_number")) for info in revisions.values())
        raise ValueError(
            f"Patchset {patchset_number} not found. Available patchsets: {', '.join(available)}"
        )

    if not current_revision:
        raise ValueError(
            f"Unable to determine current revision for change {change_id}."
        )
    return current_revision


def make_gerrit_rest_request(
    ctx: Context,
    endpoint: str,
    *,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    json_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Make a REST API request to Gerrit and handle the response."""
    gerrit_ctx = ctx.request_context.lifespan_context

    if not gerrit_ctx.http_password:
        logger.error("HTTP password not set in context")
        raise ValueError(
            "HTTP password not set. Please set GERRIT_HTTP_PASSWORD in your environment."
        )

    if not endpoint.startswith("a/"):
        endpoint = f"a/{endpoint}"

    url = f"https://{gerrit_ctx.host}/{endpoint}"
    auth = create_auth_handler(gerrit_ctx.user, gerrit_ctx.http_password)

    try:
        headers = {"Accept": "application/json", "User-Agent": "GerritReviewMCP/1.0"}

        response = requests.request(
            method,
            url,
            auth=auth,
            headers=headers,
            params=params,
            json=json_payload,
            verify=gerrit_ctx.verify_ssl,
            timeout=DEFAULT_REQUEST_TIMEOUT,
        )

        if response.status_code == 401:
            raise Exception(
                "Authentication failed. Please check your Gerrit HTTP password in your account settings."
            )

        response.raise_for_status()

        content = response.text
        if content.startswith(")]}'"):
            content = content[4:]
        content = content.strip()
        if not content:
            return {}

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
            raise Exception(f"Failed to parse Gerrit response as JSON: {str(e)}")

    except requests.exceptions.RequestException as e:
        logger.error(f"REST request failed: {str(e)}")
        response = getattr(e, "response", None)
        if response is not None:
            logger.error(f"Response status: {response.status_code}")
        raise Exception(f"Failed to make Gerrit REST API request: {str(e)}")


@asynccontextmanager
async def gerrit_lifespan(server: FastMCP) -> AsyncIterator[GerritContext]:
    """Manage Gerrit connection details."""
    host = os.getenv("GERRIT_HOST", "")
    user = os.getenv("GERRIT_USER", "")

    if host.startswith(("http://", "https://")):
        logger.warning("GERRIT_HOST should not include protocol; stripping scheme.")
        host = re.sub(r"^https?://", "", host).rstrip("/")

    if not all([host, user]):
        logger.error("Missing required environment variables:")
        if not host:
            logger.error("- GERRIT_HOST not set")
        if not user:
            logger.error("- GERRIT_USER not set")
        raise ValueError(
            "Missing required environment variables: GERRIT_HOST, GERRIT_USER. "
            "Please set these in your environment or .env file."
        )

    try:
        password = get_password()
    except ValueError as e:
        logger.error(f"Password configuration error: {str(e)}")
        raise

    verify_ssl = resolve_ssl_verification_setting()

    ctx = GerritContext(
        host=host, user=user, http_password=password, verify_ssl=verify_ssl
    )
    try:
        yield ctx
    finally:
        pass


# Create MCP server
mcp = FastMCP(
    "Gerrit Review",
    lifespan=gerrit_lifespan,
    dependencies=["python-dotenv", "requests"],
)


@mcp.tool()
def fetch_gerrit_change(
    ctx: Context,
    change_id: str,
    patchset_number: Optional[str] = None,
    include_comments: bool = False,
) -> Dict[str, Any]:
    """
    Fetch a Gerrit change and its contents.

    Args:
      change_id: The Gerrit change ID to fetch
      patchset_number: Optional patchset number to fetch (defaults to latest)
      include_comments: Optional boolean to include inline comments (defaults to False)
    Returns:
      Dict containing the raw change information including files and diffs
    """
    change_endpoint = f"a/changes/{change_id}/detail?o=CURRENT_REVISION&o=CURRENT_COMMIT&o=MESSAGES&o=DETAILED_LABELS&o=DETAILED_ACCOUNTS&o=ALL_REVISIONS&o=ALL_COMMITS&o=ALL_FILES&o=COMMIT_FOOTERS"
    change_info = make_gerrit_rest_request(ctx, change_endpoint)

    if not change_info:
        raise ValueError(f"Change {change_id} not found")

    project = change_info.get("project")
    if not project:
        raise ValueError("Project information not found in change")

    current_revision = change_info.get("current_revision")
    revisions = change_info.get("revisions", {})

    if patchset_number:
        target_revision = None
        for rev, rev_info in revisions.items():
            if str(rev_info.get("_number")) == str(patchset_number):
                target_revision = rev
                break
        if not target_revision:
            available_patchsets = sorted(
                [str(info.get("_number")) for info in revisions.values()]
            )
            raise ValueError(
                f"Patchset {patchset_number} not found. Available patchsets: {', '.join(available_patchsets)}"
            )
    else:
        target_revision = current_revision

    if not target_revision or target_revision not in revisions:
        raise ValueError("Revision information not found")

    revision_info = revisions[target_revision]

    processed_files = []
    excluded_files = []

    excluded_patterns_str = os.getenv("GERRIT_EXCLUDED_PATTERNS", "")
    if excluded_patterns_str:
        excluded_patterns = [
            pattern.strip()
            for pattern in excluded_patterns_str.split(",")
            if pattern.strip()
        ]
    else:
        excluded_patterns = []

    for file_path, file_info in revision_info.get("files", {}).items():
        if file_path == "/COMMIT_MSG":
            continue

        should_exclude = False
        exclude_reason = ""

        for pattern in excluded_patterns:
            if re.search(pattern, file_path):
                should_exclude = True
                exclude_reason = f"Excluded pattern: {pattern}"
                break

        if should_exclude:
            excluded_files.append(
                {
                    "path": file_path,
                    "status": file_info.get("status", "MODIFIED"),
                    "lines_inserted": file_info.get("lines_inserted", 0),
                    "lines_deleted": file_info.get("lines_deleted", 0),
                    "size_delta": file_info.get("size_delta", 0),
                    "exclude_reason": exclude_reason,
                }
            )
            continue

        encoded_path = quote(file_path, safe="")
        diff_endpoint = f"a/changes/{change_id}/revisions/{target_revision}/files/{encoded_path}/diff"
        diff_info = make_gerrit_rest_request(ctx, diff_endpoint)

        file_data = {
            "path": file_path,
            "status": file_info.get("status", "MODIFIED"),
            "lines_inserted": file_info.get("lines_inserted", 0),
            "lines_deleted": file_info.get("lines_deleted", 0),
            "size_delta": file_info.get("size_delta", 0),
            "diff": diff_info,
        }
        processed_files.append(file_data)

    inline_comments = {}
    if include_comments:
        try:
            comments_endpoint = (
                f"a/changes/{change_id}/revisions/{target_revision}/comments"
            )
            inline_comments = make_gerrit_rest_request(ctx, comments_endpoint)
        except Exception as e:
            logger.warning(
                f"Failed to fetch inline comments for change {change_id}: {str(e)}"
            )
            inline_comments = {}

    result = {
        "change_info": change_info,
        "project": project,
        "revision": target_revision,
        "patchset": revision_info,
        "files": processed_files,
        "inline_comments": inline_comments,
    }

    if excluded_files:
        result["excluded_large_files"] = excluded_files
        result["_note"] = (
            f"Excluded {len(excluded_files)} large files to prevent infinite loops. Use fetch_patchset_diff for specific large files."
        )

    return result


@mcp.tool()
def fetch_patchset_diff(
    ctx: Context,
    change_id: str,
    base_patchset: str,
    target_patchset: str,
    file_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch differences between two patchsets of a Gerrit change.

    Args:
      change_id: The Gerrit change ID
      base_patchset: The base patchset number to compare from
      target_patchset: The target patchset number to compare to
      file_path: Optional specific file path to get diff for.
    Returns:
      Dict containing the diff information between the patchsets
    """
    change_endpoint = f"a/changes/{change_id}/detail?o=ALL_REVISIONS&o=ALL_FILES"
    change_info = make_gerrit_rest_request(ctx, change_endpoint)

    if not change_info:
        raise ValueError(f"Change {change_id} not found")

    revisions = change_info.get("revisions", {})

    base_revision = None
    target_revision = None
    for rev, rev_info in revisions.items():
        if str(rev_info.get("_number")) == str(base_patchset):
            base_revision = rev
        if str(rev_info.get("_number")) == str(target_patchset):
            target_revision = rev

    if not base_revision or not target_revision:
        available_patchsets = sorted(
            [str(info.get("_number")) for info in revisions.values()]
        )
        raise ValueError(
            f"Patchset(s) not found. Available patchsets: {', '.join(available_patchsets)}"
        )

    diff_endpoint = f"a/changes/{change_id}/revisions/{target_revision}/files"
    if base_revision:
        diff_endpoint += f"?base={base_revision}"

    files_diff = make_gerrit_rest_request(ctx, diff_endpoint)

    changed_files = {}
    for file_path, file_info in files_diff.items():
        if file_path == "/COMMIT_MSG":
            continue

        if file_info.get("status") != "SAME":
            encoded_path = quote(file_path, safe="")
            file_diff_endpoint = f"a/changes/{change_id}/revisions/{target_revision}/files/{encoded_path}/diff"
            if base_revision:
                file_diff_endpoint += f"?base={base_revision}"
            diff_info = make_gerrit_rest_request(ctx, file_diff_endpoint)

            changed_files[file_path] = {
                "status": file_info.get("status", "MODIFIED"),
                "lines_inserted": file_info.get("lines_inserted", 0),
                "lines_deleted": file_info.get("lines_deleted", 0),
                "size_delta": file_info.get("size_delta", 0),
                "diff": diff_info,
            }

    return {
        "base_revision": base_revision,
        "target_revision": target_revision,
        "base_patchset": base_patchset,
        "target_patchset": target_patchset,
        "files": changed_files,
    }


@mcp.tool()
def submit_gerrit_review(
    ctx: Context,
    change_id: str,
    message: Optional[str] = None,
    patchset_number: Optional[str] = None,
    labels: Optional[Dict[str, int]] = None,
    comments: Optional[List[Dict[str, Any]]] = None,
    notify: str = "OWNER",
) -> Dict[str, Any]:
    """Submit a review message (and optional votes/comments) to Gerrit."""

    if not any([message, labels, comments]):
        raise ValueError(
            "Review submission requires at least one of message, labels, or comments."
        )

    change_endpoint = "a/changes/{change_id}/detail?o=ALL_REVISIONS".format(
        change_id=change_id
    )
    change_info = make_gerrit_rest_request(ctx, change_endpoint)

    revisions = change_info.get("revisions", {})
    current_revision = change_info.get("current_revision")

    target_revision = None
    if patchset_number:
        for revision_hash, info in revisions.items():
            if str(info.get("_number")) == str(patchset_number):
                target_revision = revision_hash
                break
        if not target_revision:
            available = sorted(str(info.get("_number")) for info in revisions.values())
            raise ValueError(
                f"Patchset {patchset_number} not found. Available patchsets: {', '.join(available)}"
            )
    else:
        target_revision = current_revision

    if not target_revision:
        raise ValueError("Unable to determine target revision for review submission.")

    payload: Dict[str, Any] = {"notify": notify}

    if message:
        payload["message"] = message
    if labels:
        payload["labels"] = labels

    structured_comments = build_review_comments(comments)
    if structured_comments:
        payload["comments"] = structured_comments

    review_endpoint = f"a/changes/{change_id}/revisions/{target_revision}/review"
    response = make_gerrit_rest_request(
        ctx,
        review_endpoint,
        method="POST",
        json_payload=payload,
    )

    return {
        "change_id": change_id,
        "revision": target_revision,
        "submitted": response,
    }


@mcp.tool()
def create_draft_comment(
    ctx: Context,
    change_id: str,
    path: str,
    message: str,
    patchset_number: Optional[str] = None,
    line: Optional[int] = None,
    side: Optional[str] = None,
    range: Optional[Dict[str, int]] = None,
    in_reply_to: Optional[str] = None,
    unresolved: Optional[bool] = None,
) -> Dict[str, Any]:
    """Post a single draft inline comment to a Gerrit change revision.

    Draft comments are visible only to you until published. Use the Gerrit UI
    to review, prune, and publish drafts when ready.

    Args:
      ctx: MCP request context.
      change_id: The Gerrit change ID (numeric or Change-Id string).
      path: File path the comment applies to (e.g. 'src/foo.cpp').
      message: The comment text.
      patchset_number: Patchset to comment on; defaults to the current revision.
      line: Line number within the file (positive integer). Omit for file-level comments.
      side: 'REVISION' (new file, default) or 'PARENT' (base/old file).
      range: Dict with start_line, start_character, end_line, end_character for
             multi-line range comments.
      in_reply_to: ID of an existing comment this is a reply to.
      unresolved: Whether the comment should be marked as unresolved (True/False).

    Returns:
      DraftCommentInfo dict from Gerrit, including the assigned 'id' field.
    """
    # Validate inputs before making any API calls
    comment_dict: Dict[str, Any] = {
        "path": path,
        "message": message,
        "line": line,
        "side": side,
        "range": range,
        "in_reply_to": in_reply_to,
        "unresolved": unresolved,
    }
    payload = build_draft_comment_payload(comment_dict)

    revision = _resolve_revision(ctx, change_id, patchset_number)

    draft_endpoint = f"a/changes/{change_id}/revisions/{revision}/drafts"
    response = make_gerrit_rest_request(
        ctx,
        draft_endpoint,
        method="PUT",
        json_payload=payload,
    )

    return response


@mcp.tool()
def create_draft_comments(
    ctx: Context,
    change_id: str,
    comments: List[Dict[str, Any]],
    patchset_number: Optional[str] = None,
) -> Dict[str, Any]:
    """Post multiple draft inline comments to a Gerrit change revision in batch.

    Draft comments are visible only to you until published. The batch uses a
    partial-success model: individual comment API failures are collected in the
    'errors' list rather than aborting the entire batch.

    All comments are validated upfront before any API calls are made, so schema
    errors will raise ValueError without creating any drafts.

    Args:
      ctx: MCP request context.
      change_id: The Gerrit change ID.
      comments: List of comment dicts, each with at minimum:
                - path (str): file path
                - message (str): comment text
                Optional fields per comment: line, side, range, in_reply_to, unresolved.
      patchset_number: Patchset to comment on; defaults to the current revision.

    Returns:
      Dict with keys:
        change_id, revision, total, succeeded, failed,
        created (list of DraftCommentInfo dicts),
        errors (list of {path, message, error} dicts for failures).
    """
    if not comments:
        raise ValueError(
            "create_draft_comments requires a non-empty list of comment dicts."
        )

    # Validate all comments upfront before making any API calls
    validated_payloads = []
    for idx, comment in enumerate(comments, start=1):
        validated_payloads.append(build_draft_comment_payload(comment, index=idx))

    revision = _resolve_revision(ctx, change_id, patchset_number)
    draft_endpoint = f"a/changes/{change_id}/revisions/{revision}/drafts"

    created = []
    errors = []

    for payload in validated_payloads:
        try:
            result = make_gerrit_rest_request(
                ctx,
                draft_endpoint,
                method="PUT",
                json_payload=payload,
            )
            created.append(result)
        except Exception as exc:
            errors.append({
                "path": payload.get("path"),
                "message": payload.get("message"),
                "error": str(exc),
            })

    return {
        "change_id": change_id,
        "revision": revision,
        "total": len(validated_payloads),
        "succeeded": len(created),
        "failed": len(errors),
        "created": created,
        "errors": errors,
    }


def main() -> None:
    """Entry point for the gerrit-review-mcp console script."""
    logger.info("Starting Gerrit Review MCP server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
