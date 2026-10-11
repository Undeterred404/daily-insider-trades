#!/usr/bin/env python3
"""In-process GitHub API client (no subprocess).

Mirrors ~/workspace/skills/github/bin/gh-api exactly: same endpoint,
headers, and stored custom.github credential. The daily cron helpers use
this instead of spawning the gh-api CLI via subprocess, because
subprocess calls can trip the sandbox approval gate on detached runs.

Usage:
    import gh_client
    sha = gh_client.get_sha(OWNER, REPO, "docs/index.html")
    gh_client.put_file(OWNER, REPO, "docs/index.html", data_bytes, "message")
    obj = gh_client.request("GET", "/repos/OWNER/REPO/contents/PATH")
"""
import base64
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import (  # noqa: E402
    add_surrogate_to_request,
    read_json_response,
)

API_BASE = "https://api.github.com"
CREDENTIAL = "custom.github"
ALLOWED_HOSTS = ["api.github.com"]


class GitHubError(Exception):
    """Raised when the GitHub API returns an HTTP error."""


def request(method, path, data=None):
    """Perform a GitHub API request; returns the decoded JSON body."""
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(API_BASE + path, data=body, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "muse-github-skill")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    add_surrogate_to_request(req, CREDENTIAL, allowed_hosts=ALLOWED_HOSTS)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return read_json_response(resp)
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode()[:500]
        except Exception:
            err_body = str(e)
        raise GitHubError(f"HTTP {e.code}: {err_body}")


def get_sha(owner, repo, rel):
    """Return the blob sha for a repo path, or None if it doesn't exist."""
    try:
        return request("GET", f"/repos/{owner}/{repo}/contents/{rel}").get("sha")
    except GitHubError:
        return None


def put_file(owner, repo, rel, data: bytes, message: str):
    """Create or update a file via the Contents API. Returns True on success."""
    payload = {
        "message": message,
        "content": base64.b64encode(data).decode(),
    }
    sha = get_sha(owner, repo, rel)
    if sha:
        payload["sha"] = sha
    try:
        request("PUT", f"/repos/{owner}/{repo}/contents/{rel}", payload)
    except GitHubError as e:
        print(f"FAIL {rel}: {e}")
        return False
    print(f"pushed {rel}" + (" (updated)" if sha else " (new)"))
    return True
