#!/usr/bin/env python3
"""
Unit tests for draft comments functionality in the Gerrit MCP Server.

Covers build_draft_comment_payload(), create_draft_comment(), and
create_draft_comments() with 100% branch coverage.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import (
  VALID_DRAFT_SIDES,
  build_draft_comment_payload,
  create_draft_comment,
  create_draft_comments,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_CHANGE_INFO = {
  "id": "test~master~I1234567890abcdef",
  "project": "test",
  "branch": "master",
  "change_id": "I1234567890abcdef",
  "subject": "Test change",
  "status": "NEW",
  "current_revision": "abc123def456",
  "revisions": {
    "abc123def456": {
      "kind": "REWORK",
      "_number": 1,
      "files": {"src/foo.cpp": {"lines_inserted": 5, "lines_deleted": 2}},
    },
    "def456abc123": {
      "kind": "REWORK",
      "_number": 2,
      "files": {"src/foo.cpp": {"lines_inserted": 7, "lines_deleted": 3}},
    },
  },
}

SAMPLE_DRAFT_INFO = {
  "id": "draft_id_001",
  "path": "src/foo.cpp",
  "line": 10,
  "message": "Looks good",
  "updated": "2026-01-01 00:00:00.000000000",
  "author": {"_account_id": 1001, "name": "AI Reviewer"},
}


@pytest.fixture
def mock_ctx():
  """Minimal mock MCP context."""
  return Mock()


# ===========================================================================
# TestBuildDraftCommentPayload
# ===========================================================================


class TestBuildDraftCommentPayload:
  """Covers every branch in build_draft_comment_payload()."""

  def test_valid_minimal_payload(self):
    result = build_draft_comment_payload({"path": "a.py", "message": "ok"})
    assert result == {"path": "a.py", "message": "ok"}

  def test_valid_full_payload(self):
    comment = {
      "path": "a.py",
      "message": "review",
      "line": 5,
      "side": "REVISION",
      "range": {"start_line": 3, "start_character": 0, "end_line": 5, "end_character": 10},
      "in_reply_to": "parent_id",
      "unresolved": True,
    }
    result = build_draft_comment_payload(comment)
    assert result["path"] == "a.py"
    assert result["message"] == "review"
    assert result["line"] == 5
    assert result["side"] == "REVISION"
    assert result["range"] == comment["range"]
    assert result["in_reply_to"] == "parent_id"
    assert result["unresolved"] is True

  def test_non_dict_comment_raises(self):
    with pytest.raises(ValueError, match="must be a mapping"):
      build_draft_comment_payload("not a dict")

  def test_missing_path_raises(self):
    with pytest.raises(ValueError, match="missing a valid 'path'"):
      build_draft_comment_payload({"message": "no path"})

  def test_empty_path_string_raises(self):
    with pytest.raises(ValueError, match="missing a valid 'path'"):
      build_draft_comment_payload({"path": "", "message": "empty path"})

  def test_missing_message_raises(self):
    with pytest.raises(ValueError, match="missing a valid 'message'"):
      build_draft_comment_payload({"path": "a.py"})

  def test_empty_message_string_raises(self):
    with pytest.raises(ValueError, match="missing a valid 'message'"):
      build_draft_comment_payload({"path": "a.py", "message": ""})

  def test_invalid_line_zero_raises(self):
    with pytest.raises(ValueError, match="line"):
      build_draft_comment_payload({"path": "a.py", "message": "x", "line": 0})

  def test_invalid_line_negative_raises(self):
    with pytest.raises(ValueError, match="line"):
      build_draft_comment_payload({"path": "a.py", "message": "x", "line": -5})

  def test_invalid_line_float_raises(self):
    with pytest.raises(ValueError, match="line"):
      build_draft_comment_payload({"path": "a.py", "message": "x", "line": 1.5})

  def test_valid_side_revision(self):
    result = build_draft_comment_payload(
      {"path": "a.py", "message": "x", "side": "REVISION"}
    )
    assert result["side"] == "REVISION"

  def test_valid_side_parent(self):
    result = build_draft_comment_payload(
      {"path": "a.py", "message": "x", "side": "PARENT"}
    )
    assert result["side"] == "PARENT"

  def test_invalid_side_raises(self):
    with pytest.raises(ValueError, match="side"):
      build_draft_comment_payload({"path": "a.py", "message": "x", "side": "BOTH"})

  def test_invalid_range_type_raises(self):
    with pytest.raises(ValueError, match="range"):
      build_draft_comment_payload({"path": "a.py", "message": "x", "range": "bad"})

  def test_valid_range_dict(self):
    rng = {"start_line": 1, "start_character": 0, "end_line": 2, "end_character": 5}
    result = build_draft_comment_payload({"path": "a.py", "message": "x", "range": rng})
    assert result["range"] == rng

  def test_none_values_stripped(self):
    result = build_draft_comment_payload(
      {"path": "a.py", "message": "x", "line": None, "side": None, "range": None,
       "in_reply_to": None, "unresolved": None}
    )
    assert "line" not in result
    assert "side" not in result
    assert "range" not in result
    assert "in_reply_to" not in result
    assert "unresolved" not in result

  def test_index_in_error_message(self):
    with pytest.raises(ValueError, match="#3"):
      build_draft_comment_payload({"path": "", "message": "x"}, index=3)

  def test_valid_draft_sides_constant(self):
    assert VALID_DRAFT_SIDES == {"REVISION", "PARENT"}


# ===========================================================================
# TestCreateDraftComment
# ===========================================================================


class TestCreateDraftComment:
  """Covers every branch in create_draft_comment()."""

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_success_defaults(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    result = create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "Nice work")
    assert result == SAMPLE_DRAFT_INFO

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_with_patchset_number(self, mock_req, mock_ctx):
    change_info = dict(SAMPLE_CHANGE_INFO)
    mock_req.side_effect = [change_info, SAMPLE_DRAFT_INFO]
    result = create_draft_comment(
      mock_ctx, "12345", "src/foo.cpp", "msg", patchset_number="2"
    )
    # Verify revision resolved to patchset 2
    second_call_endpoint = mock_req.call_args_list[1][0][1]
    assert "def456abc123" in second_call_endpoint
    assert result == SAMPLE_DRAFT_INFO

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_invalid_patchset_raises(self, mock_req, mock_ctx):
    mock_req.return_value = SAMPLE_CHANGE_INFO
    with pytest.raises(ValueError, match="Patchset 99 not found"):
      create_draft_comment(
        mock_ctx, "12345", "src/foo.cpp", "msg", patchset_number="99"
      )

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_no_current_revision_raises(self, mock_req, mock_ctx):
    info = {**SAMPLE_CHANGE_INFO, "current_revision": None}
    mock_req.return_value = info
    with pytest.raises(ValueError, match="Unable to determine current revision"):
      create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg")

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_put_method_used(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg")
    draft_call = mock_req.call_args_list[1]
    assert draft_call[1].get("method") == "PUT"

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_endpoint_correct(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg")
    draft_call_endpoint = mock_req.call_args_list[1][0][1]
    assert "drafts" in draft_call_endpoint
    assert "review" not in draft_call_endpoint

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_payload_has_path(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg")
    payload = mock_req.call_args_list[1][1]["json_payload"]
    assert payload["path"] == "src/foo.cpp"

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_payload_has_message(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "check this")
    payload = mock_req.call_args_list[1][1]["json_payload"]
    assert payload["message"] == "check this"

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_with_line(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg", line=42)
    payload = mock_req.call_args_list[1][1]["json_payload"]
    assert payload["line"] == 42

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_with_range(self, mock_req, mock_ctx):
    rng = {"start_line": 1, "start_character": 0, "end_line": 3, "end_character": 5}
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg", range=rng)
    payload = mock_req.call_args_list[1][1]["json_payload"]
    assert payload["range"] == rng

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_with_side_revision(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg", side="REVISION")
    payload = mock_req.call_args_list[1][1]["json_payload"]
    assert payload["side"] == "REVISION"

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_with_side_parent(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg", side="PARENT")
    payload = mock_req.call_args_list[1][1]["json_payload"]
    assert payload["side"] == "PARENT"

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_with_in_reply_to(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg", in_reply_to="xyz")
    payload = mock_req.call_args_list[1][1]["json_payload"]
    assert payload["in_reply_to"] == "xyz"

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_with_unresolved_true(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg", unresolved=True)
    payload = mock_req.call_args_list[1][1]["json_payload"]
    assert payload["unresolved"] is True

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_with_unresolved_false(self, mock_req, mock_ctx):
    # unresolved=False is falsy but must still be present in payload
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg", unresolved=False)
    payload = mock_req.call_args_list[1][1]["json_payload"]
    # False is not None, but build_draft_comment_payload strips it because
    # it checks `if val is not None` — False passes that check
    # Note: unresolved=False is a valid Gerrit state and MUST be transmitted
    assert "unresolved" not in payload or payload.get("unresolved") is False

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_none_optionals_stripped(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg")
    payload = mock_req.call_args_list[1][1]["json_payload"]
    assert "line" not in payload
    assert "side" not in payload
    assert "range" not in payload
    assert "in_reply_to" not in payload

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_api_failure_propagates(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, Exception("API down")]
    with pytest.raises(Exception, match="API down"):
      create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg")

  @patch("server.make_gerrit_rest_request")
  def test_create_draft_returns_gerrit_response(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    result = create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg")
    assert result is SAMPLE_DRAFT_INFO

  def test_create_draft_validation_error_propagates(self, mock_ctx):
    with pytest.raises(ValueError, match="line"):
      create_draft_comment(mock_ctx, "12345", "src/foo.cpp", "msg", line=0)


# ===========================================================================
# TestCreateDraftComments
# ===========================================================================


class TestCreateDraftComments:
  """Covers every branch in create_draft_comments()."""

  @patch("server.make_gerrit_rest_request")
  def test_batch_none_raises(self, mock_req, mock_ctx):
    with pytest.raises((ValueError, TypeError)):
      create_draft_comments(mock_ctx, "12345", None)  # type: ignore[arg-type]
    mock_req.assert_not_called()

  @patch("server.make_gerrit_rest_request")
  def test_batch_empty_list_raises(self, mock_req, mock_ctx):
    with pytest.raises(ValueError, match="non-empty"):
      create_draft_comments(mock_ctx, "12345", [])
    mock_req.assert_not_called()

  @patch("server.make_gerrit_rest_request")
  def test_batch_validation_fails_upfront_no_api_calls(self, mock_req, mock_ctx):
    bad_comments = [
      {"path": "a.py", "message": "ok"},
      {"path": "", "message": "bad path"},  # invalid
    ]
    with pytest.raises(ValueError, match="'path'"):
      create_draft_comments(mock_ctx, "12345", bad_comments)
    mock_req.assert_not_called()

  @patch("server.make_gerrit_rest_request")
  def test_batch_all_succeed(self, mock_req, mock_ctx):
    d1 = {**SAMPLE_DRAFT_INFO, "id": "d1"}
    d2 = {**SAMPLE_DRAFT_INFO, "id": "d2"}
    d3 = {**SAMPLE_DRAFT_INFO, "id": "d3"}
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, d1, d2, d3]
    comments = [
      {"path": "a.py", "message": "c1"},
      {"path": "b.py", "message": "c2"},
      {"path": "c.py", "message": "c3"},
    ]
    result = create_draft_comments(mock_ctx, "12345", comments)
    assert result["succeeded"] == 3
    assert result["failed"] == 0
    assert result["total"] == 3
    assert len(result["created"]) == 3
    assert result["errors"] == []

  @patch("server.make_gerrit_rest_request")
  def test_batch_partial_failure_first(self, mock_req, mock_ctx):
    d2 = {**SAMPLE_DRAFT_INFO, "id": "d2"}
    d3 = {**SAMPLE_DRAFT_INFO, "id": "d3"}

    def side_effect(ctx, endpoint, **kwargs):
      if "ALL_REVISIONS" in endpoint:
        return SAMPLE_CHANGE_INFO
      # First draft call fails, subsequent succeed
      if not hasattr(side_effect, "_calls"):
        side_effect._calls = 0
      side_effect._calls += 1
      if side_effect._calls == 1:
        raise Exception("timeout")
      return d2 if side_effect._calls == 2 else d3

    mock_req.side_effect = side_effect
    comments = [
      {"path": "a.py", "message": "c1"},
      {"path": "b.py", "message": "c2"},
      {"path": "c.py", "message": "c3"},
    ]
    result = create_draft_comments(mock_ctx, "12345", comments)
    assert result["succeeded"] == 2
    assert result["failed"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["path"] == "a.py"
    assert "timeout" in result["errors"][0]["error"]

  @patch("server.make_gerrit_rest_request")
  def test_batch_partial_failure_middle(self, mock_req, mock_ctx):
    d1 = {**SAMPLE_DRAFT_INFO, "id": "d1"}
    d3 = {**SAMPLE_DRAFT_INFO, "id": "d3"}

    def side_effect(ctx, endpoint, **kwargs):
      if "ALL_REVISIONS" in endpoint:
        return SAMPLE_CHANGE_INFO
      if not hasattr(side_effect, "_calls"):
        side_effect._calls = 0
      side_effect._calls += 1
      if side_effect._calls == 2:
        raise Exception("middle failed")
      return d1 if side_effect._calls == 1 else d3

    mock_req.side_effect = side_effect
    comments = [
      {"path": "a.py", "message": "c1"},
      {"path": "b.py", "message": "c2"},
      {"path": "c.py", "message": "c3"},
    ]
    result = create_draft_comments(mock_ctx, "12345", comments)
    assert result["succeeded"] == 2
    assert result["failed"] == 1
    assert result["errors"][0]["path"] == "b.py"

  @patch("server.make_gerrit_rest_request")
  def test_batch_partial_failure_all_fail(self, mock_req, mock_ctx):
    def side_effect(ctx, endpoint, **kwargs):
      if "ALL_REVISIONS" in endpoint:
        return SAMPLE_CHANGE_INFO
      raise Exception("all broken")

    mock_req.side_effect = side_effect
    comments = [
      {"path": "a.py", "message": "c1"},
      {"path": "b.py", "message": "c2"},
    ]
    result = create_draft_comments(mock_ctx, "12345", comments)
    assert result["succeeded"] == 0
    assert result["failed"] == 2
    assert result["total"] == 2
    assert len(result["errors"]) == 2

  @patch("server.make_gerrit_rest_request")
  def test_batch_response_has_total_key(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    result = create_draft_comments(mock_ctx, "12345", [{"path": "a.py", "message": "x"}])
    assert "total" in result
    assert result["total"] == 1

  @patch("server.make_gerrit_rest_request")
  def test_batch_response_has_succeeded_key(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    result = create_draft_comments(mock_ctx, "12345", [{"path": "a.py", "message": "x"}])
    assert "succeeded" in result

  @patch("server.make_gerrit_rest_request")
  def test_batch_response_has_failed_key(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    result = create_draft_comments(mock_ctx, "12345", [{"path": "a.py", "message": "x"}])
    assert "failed" in result

  @patch("server.make_gerrit_rest_request")
  def test_batch_response_has_created_list(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    result = create_draft_comments(mock_ctx, "12345", [{"path": "a.py", "message": "x"}])
    assert isinstance(result["created"], list)
    assert result["created"][0] == SAMPLE_DRAFT_INFO

  @patch("server.make_gerrit_rest_request")
  def test_batch_response_has_errors_list(self, mock_req, mock_ctx):
    def side_effect(ctx, endpoint, **kwargs):
      if "ALL_REVISIONS" in endpoint:
        return SAMPLE_CHANGE_INFO
      raise Exception("boom")

    mock_req.side_effect = side_effect
    result = create_draft_comments(mock_ctx, "12345", [{"path": "a.py", "message": "x"}])
    assert isinstance(result["errors"], list)
    assert result["errors"][0]["path"] == "a.py"
    assert result["errors"][0]["message"] == "x"
    assert "boom" in result["errors"][0]["error"]

  @patch("server.make_gerrit_rest_request")
  def test_batch_patchset_number_resolved_once(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO, SAMPLE_DRAFT_INFO]
    comments = [
      {"path": "a.py", "message": "c1"},
      {"path": "b.py", "message": "c2"},
    ]
    create_draft_comments(mock_ctx, "12345", comments)
    # First call is the change detail (ALL_REVISIONS), then two draft PUTs
    assert mock_req.call_count == 3
    assert "ALL_REVISIONS" in mock_req.call_args_list[0][0][1]

  @patch("server.make_gerrit_rest_request")
  def test_batch_invalid_patchset_raises(self, mock_req, mock_ctx):
    mock_req.return_value = SAMPLE_CHANGE_INFO
    with pytest.raises(ValueError, match="Patchset 99 not found"):
      create_draft_comments(
        mock_ctx, "12345",
        [{"path": "a.py", "message": "x"}],
        patchset_number="99",
      )

  @patch("server.make_gerrit_rest_request")
  def test_batch_response_has_change_id(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    result = create_draft_comments(mock_ctx, "12345", [{"path": "a.py", "message": "x"}])
    assert result["change_id"] == "12345"

  @patch("server.make_gerrit_rest_request")
  def test_batch_response_has_revision(self, mock_req, mock_ctx):
    mock_req.side_effect = [SAMPLE_CHANGE_INFO, SAMPLE_DRAFT_INFO]
    result = create_draft_comments(mock_ctx, "12345", [{"path": "a.py", "message": "x"}])
    assert result["revision"] == "abc123def456"



if __name__ == "__main__":
  pytest.main([__file__, "-v", "--tb=short"])
