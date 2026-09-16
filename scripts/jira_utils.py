"""
Core utilities for interacting with the Jira REST API.

This module provides low-level API access functions with retry logic and error handling.
Environment variables (accepts either naming convention):
- JIRA_URL or JIRA_BASE_URL: Base URL for the Jira instance (required)
- JIRA_USER or JIRA_EMAIL: Username or email for authentication (required)
- JIRA_TOKEN or JIRA_API_TOKEN: API token for authentication (required)
"""

import os
import sys
import time
from typing import Any
from urllib.parse import quote, urlparse

import requests

from scripts.utils.error_utils import exit_error

_ENV_ALIASES = {
    "JIRA_URL": "JIRA_BASE_URL",
    "JIRA_USER": "JIRA_EMAIL",
    "JIRA_TOKEN": "JIRA_API_TOKEN",
}


class AttachmentFetchError(Exception):
    """Raised when a Jira attachment URL cannot be validated or downloaded."""


class JiraConfigurationError(AttachmentFetchError):
    """Raised when Jira configuration is missing for a library-level request."""


def _jira_auth() -> tuple[str, str]:
    """Return the configured Jira credentials for authenticated requests."""
    return require_env("JIRA_USER", exit_on_missing=False), require_env("JIRA_TOKEN", exit_on_missing=False)


def require_env(var_name: str, *, exit_on_missing: bool = True) -> str:
    """
    Require an environment variable to be set.

    Supports aliases: JIRA_URL/JIRA_BASE_URL, JIRA_USER/JIRA_EMAIL,
    JIRA_TOKEN/JIRA_API_TOKEN. The canonical name is checked first,
    then the alias.

    Args:
        var_name: Name of the environment variable
        exit_on_missing: Exit through ``exit_error`` when true; otherwise raise
            ``JiraConfigurationError`` for library callers.

    Returns:
        The value of the environment variable

    Raises:
        SystemExit: If neither the variable nor its alias is set and ``exit_on_missing`` is true
        JiraConfigurationError: If neither the variable nor its alias is set and
            ``exit_on_missing`` is false
    """
    value = os.getenv(var_name)
    if not value:
        alias = _ENV_ALIASES.get(var_name)
        if alias:
            value = os.getenv(alias)
    if not value:
        alias = _ENV_ALIASES.get(var_name, "")
        hint = f" (or {alias})" if alias else ""
        if not exit_on_missing:
            raise JiraConfigurationError(f"Jira configuration is missing: {var_name}")
        exit_error(f"Error: {var_name}{hint} environment variable is required")
    return value


def make_request(
    method: str,
    endpoint: str,
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> requests.Response:
    """
    Make an HTTP request to the Jira API.

    Args:
        method: HTTP method (GET, POST, PUT, etc.)
        endpoint: API endpoint path (e.g., '/rest/api/2/issue/PROJ-123')
        json_data: Optional JSON body for the request
        params: Optional query parameters

    Returns:
        The response object

    Raises:
        requests.HTTPError: If the request fails
    """
    jira_url = require_env("JIRA_URL", exit_on_missing=False)
    url = f"{jira_url.rstrip('/')}{endpoint}"

    response = requests.request(
        method=method,
        url=url,
        auth=_jira_auth(),
        headers={"Content-Type": "application/json"},
        json=json_data,
        params=params,
        timeout=60,
    )

    response.raise_for_status()
    return response


def api_call(
    endpoint: str,
    method: str = "GET",
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Make a Jira API call and return the JSON response.

    Args:
        endpoint: API endpoint path
        method: HTTP method (default: GET)
        json_data: Optional JSON body
        params: Optional query parameters

    Returns:
        The JSON response as a dictionary, or None for empty responses (e.g., 204 No Content)

    Raises:
        requests.HTTPError: If the request fails
    """
    response = make_request(method, endpoint, json_data, params)

    # Handle empty responses (e.g., 204 No Content from PUT/DELETE)
    if response.status_code == 204 or not response.content:
        return None

    return response.json()


def api_call_with_retry(
    endpoint: str,
    method: str = "GET",
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> dict[str, Any] | None:
    """
    Make a Jira API call with exponential backoff retry logic.

    Args:
        endpoint: API endpoint path
        method: HTTP method (default: GET)
        json_data: Optional JSON body
        params: Optional query parameters
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay: Initial delay between retries in seconds (default: 1.0)

    Returns:
        The JSON response as a dictionary

    Raises:
        requests.HTTPError: If all retries fail
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            return api_call(endpoint, method, json_data, params)
        except requests.HTTPError as e:
            last_exception = e

            # Don't retry auth errors (401, 403) - credentials won't fix themselves
            if e.response.status_code in (401, 403):
                # For auth errors, we still want to raise the exception rather than exit
                # since callers may want to handle it, so keep this as a print
                print(
                    f"Authentication error ({e.response.status_code}): Check JIRA_URL, JIRA_USER, JIRA_TOKEN",
                    file=sys.stderr,
                )
                raise

            # Don't retry other 4xx errors (client errors like 404, 400)
            if e.response.status_code < 500:
                raise

            # Retry 5xx server errors (transient issues)
            if attempt < max_retries - 1:
                delay = retry_delay * (2**attempt)
                print(f"Request failed (attempt {attempt + 1}/{max_retries}), retrying in {delay}s...", file=sys.stderr)
                time.sleep(delay)

    # All retries failed
    raise last_exception


def get_issue(issue_key: str, fields: str | None = None) -> dict[str, Any]:
    """
    Fetch a Jira issue by key.

    Args:
        issue_key: The Jira issue key (e.g., 'PROJ-123')
        fields: Optional comma-separated list of fields to return

    Returns:
        The issue data as a dictionary

    Raises:
        requests.HTTPError: If the request fails
    """
    params = {}
    if fields:
        params["fields"] = fields

    endpoint = f"/rest/api/2/issue/{quote(issue_key, safe='')}"
    return api_call_with_retry(endpoint, params=params)


def _url_origin(url: str) -> tuple[str, str, int | None]:
    """Return the normalized scheme, hostname, and effective port for an absolute URL."""
    if not isinstance(url, str):
        raise ValueError("URL must be absolute")

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError("URL must have a valid origin") from exc

    scheme = parsed.scheme.lower()
    if not scheme or not parsed.netloc or not hostname:
        raise ValueError("URL must be absolute")

    if port is None:
        port = {"http": 80, "https": 443}.get(scheme)

    return scheme, hostname.casefold(), port


def download_attachment(content_url: str) -> str:
    """Download same-origin Jira attachment content using configured credentials.

    The attachment URL must be absolute, use HTTPS, and have the same scheme, host,
    and effective port as ``JIRA_URL``. This validation happens before credentials
    are loaded or attached to the request. ``JIRA_URL``/``JIRA_BASE_URL`` and
    ``JIRA_USER``/``JIRA_EMAIL`` and ``JIRA_TOKEN``/``JIRA_API_TOKEN`` aliases remain
    supported through the shared environment helper.

    Args:
        content_url: Absolute Jira attachment ``content`` URL from an issue payload

    Returns:
        The attachment body as text

    Raises:
        AttachmentFetchError: If the URL is malformed, is not the configured Jira
            origin, or the attachment cannot be downloaded
    """
    try:
        jira_url = require_env("JIRA_URL", exit_on_missing=False)
        content_origin = _url_origin(content_url)
        if content_origin[0] != "https":
            raise ValueError("attachment URL must use HTTPS")
        if content_origin != _url_origin(jira_url):
            raise ValueError("attachment URL origin does not match configured Jira URL")

        response = requests.get(
            content_url,
            auth=_jira_auth(),
            timeout=60,
        )
        response.raise_for_status()
        return response.text
    except (ValueError, requests.RequestException) as exc:
        raise AttachmentFetchError("Jira attachment fetch failed") from exc


def add_labels(issue_key: str, labels: list[str], remove: list[str] | None = None) -> None:
    """
    Add labels to a Jira issue, optionally dropping a set of stale labels first.

    This function fetches the current labels, drops any in `remove`, then merges
    in `labels` to avoid clobbering unrelated existing labels. Preserves label
    order and only makes API calls when labels actually change.

    Args:
        issue_key: The Jira issue key (e.g., 'PROJ-123')
        labels: List of labels to add
        remove: Optional list of labels to strip before adding, e.g. a previous
            state label superseded by one of `labels` (rubric verdict labels are
            mutually exclusive — an issue must never carry more than one at once)

    Raises:
        requests.HTTPError: If the request fails
    """
    # Fetch current issue to get existing labels
    issue = get_issue(issue_key, fields="labels")
    existing_labels = issue.get("fields", {}).get("labels", [])

    # Drop stale labels, then merge in the new ones preserving order (append at end, deduplicate)
    all_labels = [label for label in existing_labels if label not in (remove or [])]
    for label in labels:
        if label not in all_labels:
            all_labels.append(label)

    # Only update if labels actually changed
    if all_labels == existing_labels:
        return

    # Update the issue (returns None for 204 No Content)
    endpoint = f"/rest/api/2/issue/{quote(issue_key, safe='')}"
    update_data = {"fields": {"labels": all_labels}}

    api_call_with_retry(endpoint, method="PUT", json_data=update_data)
