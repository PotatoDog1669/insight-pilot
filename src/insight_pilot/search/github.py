"""GitHub search module."""
from __future__ import annotations

import re
import time
from typing import Dict, Iterable, List, Optional

import requests

from insight_pilot.errors import SkillError, classify_request_error
from insight_pilot.models import utc_now_iso

BASE_URL = "https://api.github.com"
SEARCH_URL = f"{BASE_URL}/search"

DEFAULT_ACCEPT = ",".join([
    "application/vnd.github+json",
    "application/vnd.github.mercy-preview+json",
    "application/vnd.github.v3.text-match+json",
])


def build_headers(token: Optional[str] = None, accept: str = DEFAULT_ACCEPT) -> Dict[str, str]:
    """Build GitHub API headers."""
    headers = {
        "Accept": accept,
        "User-Agent": "Insight-Pilot/0.3",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def request_with_backoff(
    url: str,
    params: Dict[str, str],
    headers: Dict[str, str],
    max_retries: int,
) -> requests.Response:
    """Request with exponential backoff."""
    delay = 1.0
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=60)
            if response.status_code in {403, 429, 500, 502, 503, 504}:
                if attempt == max_retries - 1:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    time.sleep(float(retry_after))
                else:
                    time.sleep(delay)
                    delay = min(delay * 2, 60)
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt == max_retries - 1:
                raise SkillError(
                    message=str(exc),
                    code=classify_request_error(exc),
                ) from exc
            time.sleep(delay)
            delay = min(delay * 2, 60)

    raise last_error or RuntimeError("Unreachable request retry state")


def paginate_search(
    endpoint: str,
    query: str,
    limit: int,
    headers: Dict[str, str],
    max_retries: int,
    extra_params: Optional[Dict[str, str]] = None,
) -> List[Dict[str, object]]:
    """Paginate GitHub search results."""
    per_page = min(100, max(1, limit))
    page = 1
    results: List[Dict[str, object]] = []
    extra_params = extra_params or {}

    while len(results) < limit:
        params = {"q": query, "per_page": str(per_page), "page": str(page)}
        params.update(extra_params)
        response = request_with_backoff(f"{SEARCH_URL}/{endpoint}", params, headers, max_retries)
        payload = response.json()
        items = payload.get("items", []) or []
        results.extend(items)

        total_count = payload.get("total_count", 0)
        if not items or len(results) >= total_count:
            break
        if page * per_page >= 1000:
            break
        page += 1

    return results[:limit]


def fetch_repo_readme(
    full_name: str,
    headers: Dict[str, str],
    max_retries: int,
    max_chars: int = 5000,
) -> Optional[str]:
    """Fetch repository README content."""
    url = f"{BASE_URL}/repos/{full_name}/readme"
    accept = "application/vnd.github.raw"
    raw_headers = dict(headers)
    raw_headers["Accept"] = accept
    response = request_with_backoff(url, {}, raw_headers, max_retries)
    text = response.text.strip()
    if not text:
        return None
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "..."
    return text


def fetch_latest_commit(full_name: str, headers: Dict[str, str], max_retries: int) -> Optional[Dict[str, str]]:
    """Fetch the latest commit metadata."""
    url = f"{BASE_URL}/repos/{full_name}/commits"
    response = request_with_backoff(url, {"per_page": "1"}, headers, max_retries)
    commits = response.json()
    if not isinstance(commits, list) or not commits:
        return None
    commit = commits[0]
    sha = commit.get("sha")
    commit_info = commit.get("commit", {}) or {}
    author = commit_info.get("author", {}) or {}
    return {
        "sha": sha,
        "date": author.get("date"),
        "message": (commit_info.get("message") or "").splitlines()[0][:200],
    }


def fetch_contributors(
    full_name: str,
    headers: Dict[str, str],
    max_retries: int,
    limit: int = 5,
) -> List[str]:
    """Fetch top contributors."""
    url = f"{BASE_URL}/repos/{full_name}/contributors"
    response = request_with_backoff(url, {"per_page": str(limit)}, headers, max_retries)
    contributors = response.json()
    if not isinstance(contributors, list):
        return []
    return [c.get("login") for c in contributors if c.get("login")][:limit]


def extract_paper_links(text: str) -> List[str]:
    """Extract paper links from README or text."""
    if not text:
        return []
    patterns = [
        r"https?://arxiv\.org/(?:abs|pdf)/[^\s)]+",
        r"https?://doi\.org/[^\s)]+",
        r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b",
    ]
    links: List[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            if match.startswith("10."):
                match = f"https://doi.org/{match}"
            if match not in links:
                links.append(match)
    return links


def transform_repo_item(
    repo: Dict[str, object],
    readme: Optional[str],
    latest_commit: Optional[Dict[str, str]],
    contributors: List[str],
) -> Dict[str, object]:
    """Transform repository payload into standard item."""
    owner = repo.get("owner", {}) or {}
    full_name = repo.get("full_name") or repo.get("name") or ""
    description = repo.get("description") or ""
    topics = repo.get("topics") or []
    readme_excerpt = readme.strip() if readme else None

    paper_links = extract_paper_links(readme or "")

    urls_other = {}
    homepage = repo.get("homepage")
    if homepage:
        urls_other["homepage"] = homepage

    return {
        "type": "github",
        "title": full_name,
        "authors": [owner.get("login")] if owner.get("login") else [],
        "date": repo.get("pushed_at") or repo.get("created_at"),
        "summary": description or None,
        "abstract": readme_excerpt,
        "identifiers": {
            "other": {
                "github_id": str(repo.get("id") or ""),
                "full_name": full_name,
            }
        },
        "urls": {
            "abstract": repo.get("html_url"),
            "publisher": homepage,
            "other": urls_other,
        },
        "metadata": {
            "stars": repo.get("stargazers_count"),
            "forks": repo.get("forks_count"),
            "topics": topics,
            "language": repo.get("language"),
            "license": (repo.get("license") or {}).get("spdx_id"),
            "latest_commit": latest_commit,
            "contributors": contributors,
            "paper_links": paper_links,
            "repo_url": repo.get("html_url"),
        },
        "source": "github",
        "download_status": "unavailable",
        "collected_at": utc_now_iso(),
    }


def transform_code_item(code: Dict[str, object]) -> Dict[str, object]:
    """Transform code search item into standard item."""
    repo = code.get("repository", {}) or {}
    full_name = repo.get("full_name") or ""
    path = code.get("path") or ""
    title = f"{full_name}:{path}" if full_name and path else (code.get("name") or "")
    text_matches = code.get("text_matches", []) or []
    snippet = ""
    if text_matches:
        fragment = text_matches[0].get("fragment") or ""
        snippet = fragment.strip()

    return {
        "type": "github",
        "title": title,
        "authors": [repo.get("owner", {}).get("login")] if repo.get("owner") else [],
        "date": repo.get("pushed_at") or repo.get("created_at"),
        "summary": snippet or None,
        "identifiers": {
            "other": {
                "github_id": str(code.get("sha") or ""),
                "repo_full_name": full_name,
                "path": path,
                "github_type": "code",
            }
        },
        "urls": {
            "abstract": code.get("html_url"),
            "publisher": repo.get("html_url"),
        },
        "metadata": {
            "repo_full_name": full_name,
            "path": path,
            "score": code.get("score"),
        },
        "source": "github",
        "download_status": "unavailable",
        "collected_at": utc_now_iso(),
    }


def transform_issue_item(issue: Dict[str, object], issue_type: str) -> Dict[str, object]:
    """Transform issue/discussion item into standard item."""
    repo_url = issue.get("repository_url") or ""
    repo_name = repo_url.split("/repos/")[-1] if "/repos/" in repo_url else ""
    repo_html = repo_url.replace("https://api.github.com/repos/", "https://github.com/")
    title = issue.get("title") or ""
    body = issue.get("body") or ""
    summary = body.strip().splitlines()[0][:200] if body else None

    return {
        "type": "github",
        "title": title,
        "authors": [issue.get("user", {}).get("login")] if issue.get("user") else [],
        "date": issue.get("created_at"),
        "summary": summary,
        "abstract": body.strip() if body else None,
        "identifiers": {
            "other": {
                "github_id": str(issue.get("id") or ""),
                "repo_full_name": repo_name,
                "github_type": issue_type,
                "issue_number": issue.get("number"),
            }
        },
        "urls": {
            "abstract": issue.get("html_url"),
            "publisher": repo_html,
        },
        "metadata": {
            "repo_full_name": repo_name,
            "state": issue.get("state"),
            "comments": issue.get("comments"),
        },
        "source": "github",
        "download_status": "unavailable",
        "collected_at": utc_now_iso(),
    }


def split_limits(total: int, groups: Iterable[str]) -> Dict[str, int]:
    """Split total limit across groups."""
    groups = list(groups)
    if not groups:
        return {}
    base = max(0, total // len(groups))
    remainder = max(0, total - base * len(groups))
    limits = {group: base for group in groups}
    for idx in range(remainder):
        limits[groups[idx]] += 1
    return limits


def search(
    query: str,
    limit: int = 50,
    types: Optional[List[str]] = None,
    token: Optional[str] = None,
    max_retries: int = 3,
    detail_limit: Optional[int] = None,
) -> List[Dict[str, object]]:
    """Search GitHub repositories, code, and issues/discussions."""
    types = types or ["repositories", "code", "issues", "discussions"]
    headers = build_headers(token)
    results: List[Dict[str, object]] = []
    limits = split_limits(limit, types)

    repo_details_limit = detail_limit
    if repo_details_limit is None:
        repo_details_limit = 20 if token else 5

    for search_type in types:
        type_limit = limits.get(search_type, 0)
        if type_limit <= 0:
            continue

        if search_type == "repositories":
            repos = paginate_search("repositories", query, type_limit, headers, max_retries)
            for idx, repo in enumerate(repos):
                if idx < repo_details_limit:
                    full_name = repo.get("full_name") or ""
                    readme = None
                    latest_commit = None
                    contributors = []
                    if full_name:
                        try:
                            readme = fetch_repo_readme(full_name, headers, max_retries)
                        except SkillError:
                            readme = None
                        try:
                            latest_commit = fetch_latest_commit(full_name, headers, max_retries)
                        except SkillError:
                            latest_commit = None
                        try:
                            contributors = fetch_contributors(full_name, headers, max_retries)
                        except SkillError:
                            contributors = []
                else:
                    readme = None
                    latest_commit = None
                    contributors = []
                results.append(transform_repo_item(repo, readme, latest_commit, contributors))

        elif search_type == "code":
            code_items = paginate_search("code", query, type_limit, headers, max_retries)
            results.extend(transform_code_item(item) for item in code_items)

        elif search_type in {"issues", "discussions"}:
            qualifier = "type:issue" if search_type == "issues" else "type:discussion"
            issue_query = f"{query} {qualifier}"
            issue_items = paginate_search("issues", issue_query, type_limit, headers, max_retries)
            results.extend(transform_issue_item(item, search_type) for item in issue_items)

    return results[:limit]
