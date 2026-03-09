"""
Configuration module for Gerrit MCP server authentication.

This module handles environment variable configuration for authentication methods
and provides factory functions for creating appropriate authentication handlers.

Supports both HTTP Digest authentication (original/default) and HTTP Basic
authentication (optional) to maintain backward compatibility while providing
flexibility for different Gerrit server configurations.
"""

import logging
import os
import re
from typing import Union

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

# Version check for requests library
try:
    from importlib.metadata import version as _dist_version

    requests_version = _dist_version("requests")
    min_required = "2.31.0"

    try:
        from packaging.version import Version as _Version
    except Exception:
        _Version = None  # type: ignore

    if _Version:
        if _Version(requests_version) < _Version(min_required):
            raise ImportError(
                f"requests library version {requests_version} is too old. "
                f"Please upgrade to requests>={min_required} for latest security patches:\n"
                f"  pip install --upgrade 'requests>={min_required}'"
            )
    else:
        version_match = re.match(r"^\s*(\d+)\.(\d+)\.(\d+)", requests_version)
        if not version_match or tuple(map(int, version_match.groups())) < (2, 31, 0):
            raise ImportError(
                f"requests library version {requests_version} is too old. "
                f"Please upgrade to requests>={min_required} for latest security patches:\n"
                f"  pip install --upgrade 'requests>={min_required}'"
            )
except Exception as e:
    logging.warning("Could not verify requests version: %s", e)

# Valid authentication methods
VALID_AUTH_METHODS = ["digest", "basic"]
DEFAULT_AUTH_METHOD = "digest"  # Maintain backward compatibility

__all__ = [
    "get_auth_method",
    "get_password",
    "create_auth_handler",
    "VALID_AUTH_METHODS",
    "DEFAULT_AUTH_METHOD",
]


def get_auth_method() -> str:
    """
    Get the authentication method from environment variables.

    Reads GERRIT_AUTH_METHOD and validates it.
    Defaults to 'digest' (HTTP Digest) for backward compatibility.

    Returns:
      str: The authentication method ('digest' or 'basic')

    Raises:
      ValueError: If the authentication method is invalid
    """
    auth_method = os.environ.get("GERRIT_AUTH_METHOD", DEFAULT_AUTH_METHOD)
    auth_method_lower = auth_method.lower()

    if auth_method_lower not in VALID_AUTH_METHODS:
        raise ValueError(
            f"Invalid authentication method: '{auth_method}'. "
            f"Must be one of {VALID_AUTH_METHODS}. "
            f"Default is '{DEFAULT_AUTH_METHOD}' (HTTP Digest)."
        )

    return auth_method_lower


def get_password() -> str:
    """
    Get the appropriate password based on the authentication method.

    Returns:
      str: The password for the selected authentication method

    Raises:
      ValueError: If the required password environment variable is not set
    """
    auth_method = get_auth_method()

    if auth_method == "basic":
        password = os.environ.get("GERRIT_PASSWORD")
        if not password:
            raise ValueError(
                "GERRIT_PASSWORD environment variable is required for HTTP Basic authentication (LDAP). "
                "Please set GERRIT_PASSWORD to your LDAP password."
            )
        return password
    else:
        password = os.environ.get("GERRIT_HTTP_PASSWORD")
        if not password:
            raise ValueError(
                "GERRIT_HTTP_PASSWORD environment variable is required for HTTP Digest authentication. "
                "Please set GERRIT_HTTP_PASSWORD to your HTTP password from Gerrit Settings > HTTP Credentials."
            )
        return password


def create_auth_handler(
    username: str, password: str
) -> Union[HTTPBasicAuth, HTTPDigestAuth]:
    """
    Create an authentication handler based on the configured method.

    Args:
      username: The username for authentication
      password: The password for authentication (should come from get_password())

    Returns:
      Union[HTTPBasicAuth, HTTPDigestAuth]: The appropriate authentication handler
    """
    auth_method = get_auth_method()

    if auth_method == "basic":
        return HTTPBasicAuth(username, password)
    else:
        return HTTPDigestAuth(username, password)
