"""Fetch a GitHub profile and return one snapshot of it, whatever the source.

With a token, a single GraphQL query brings repositories (with languages,
topics, dates and stars), the contribution calendar and the counters. Without
one, REST gives everything except the calendar. The demo fixture is a stored
GraphQL payload, so it runs through the same code as real data.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.github.com/graphql"
REST_URL = "https://api.github.com"
DEMO_FILE = Path(__file__).resolve().parent / "demo_data.json"

_REPO_FRAGMENT = """
fragment repo on Repository {
  name nameWithOwner isFork stargazerCount createdAt pushedAt description
  primaryLanguage { name }
  languages(first: 12, orderBy: {field: SIZE, direction: DESC}) { totalSize edges { size node { name } } }
  repositoryTopics(first: 12) { nodes { topic { name } } }
}"""


REST_LANGUAGE_REPOS = 40          # without a token: how many repositories have their languages read


class DataError(RuntimeError):
    """The profile could not be read."""


@dataclass(frozen=True)
class Repo:
    name: str
    owner: str
    stars: int
    created: date
    pushed: date
    description: str
    primary_language: Optional[str]
    languages: dict            # language name -> bytes
    topics: tuple
    is_fork: bool

    @property
    def key(self) -> str:
        """What tells this repository from every other: "owner/name", in lower case."""
        return f"{self.owner}/{self.name}".lower()


@dataclass(frozen=True)
class Snapshot:
    login: str
    repos: tuple               # Repo, the user's own first, then featured repositories of other owners
    weeks: Optional[tuple]     # ((first day, contributions), ...) or None without a calendar
    total_contributions: Optional[int]
    counters: dict             # stars, prs, issues, repos
    today: date


def _day(stamp: str) -> date:
    return date.fromisoformat(stamp[:10])


def _repo_from_graphql(node: dict) -> Repo:
    owner, _, name = node["nameWithOwner"].partition("/")
    return Repo(
        name=name,
        owner=owner,
        stars=node["stargazerCount"],
        created=_day(node["createdAt"]),
        pushed=_day(node["pushedAt"] or node["createdAt"]),
        description=node.get("description") or "",
        primary_language=(node.get("primaryLanguage") or {}).get("name"),
        languages={edge["node"]["name"]: edge["size"] for edge in (node.get("languages") or {}).get("edges") or []},
        topics=tuple(t["topic"]["name"] for t in (node.get("repositoryTopics") or {}).get("nodes") or []),
        is_fork=node["isFork"],
    )


def build_query(login: str, extra_repos: list) -> tuple:
    """The GraphQL query and its variables. extra_repos are "owner/name" featured projects."""
    declared, aliases, variables = ["$login: String!"], [], {"login": login}
    for i, full_name in enumerate(extra_repos):
        owner, _, name = full_name.rpartition("/")
        declared += [f"$o{i}: String!", f"$n{i}: String!"]
        aliases.append(f"  x{i}: repository(owner: $o{i}, name: $n{i}) {{ ...repo }}")
        variables[f"o{i}"], variables[f"n{i}"] = owner or login, name
    query = f"""query({", ".join(declared)}) {{
  user(login: $login) {{
    login
    pullRequests {{ totalCount }}
    issues {{ totalCount }}
    contributionsCollection {{
      contributionCalendar {{ totalContributions weeks {{ contributionDays {{ date contributionCount }} }} }}
    }}
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, first: 100,
                 orderBy: {{field: STARGAZERS, direction: DESC}}) {{
      totalCount
      nodes {{ ...repo }}
    }}
  }}
{chr(10).join(aliases)}
}}{_REPO_FRAGMENT}"""
    return query, variables


def from_graphql(payload: dict, today: date, login: Optional[str] = None) -> Snapshot:
    """Turn a GraphQL response into a snapshot."""
    body = payload.get("data") or {}
    user = body.get("user")
    if not user:
        errors = payload.get("errors") or []
        if errors:
            first = errors[0]
            raise DataError("GitHub's GraphQL API answered with an error: "
                            f"{first.get('message', first) if isinstance(first, dict) else first}")
        raise DataError(f"GitHub has no user '{login or '?'}' (or the token cannot see it).")
    owned = [_repo_from_graphql(node) for node in user["repositories"]["nodes"] if node]
    seen = {(r.owner, r.name) for r in owned}
    extras = []
    for key in sorted(k for k in body if k != "user"):
        node = body[key]
        if not node:
            continue
        repo = _repo_from_graphql(node)
        if (repo.owner, repo.name) not in seen:
            seen.add((repo.owner, repo.name))
            extras.append(repo)
    calendar = user["contributionsCollection"]["contributionCalendar"]
    weeks = tuple(
        (_day(week["contributionDays"][0]["date"]), sum(d["contributionCount"] for d in week["contributionDays"]))
        for week in calendar["weeks"] if week["contributionDays"]
    )
    return Snapshot(
        login=user["login"],
        repos=tuple(owned + extras),
        weeks=weeks,
        total_contributions=calendar["totalContributions"],
        counters={
            "stars": sum(r.stars for r in owned),
            "prs": user["pullRequests"]["totalCount"],
            "issues": user["issues"]["totalCount"],
            "repos": user["repositories"]["totalCount"],
        },
        today=today,
    )


def _rest_key(r: dict) -> str:
    return f"{r['owner']['login']}/{r['name']}".lower()


def _repo_from_rest(r: dict, languages: dict) -> Repo:
    return Repo(
        name=r["name"],
        owner=r["owner"]["login"],
        stars=r.get("stargazers_count", 0),
        created=_day(r["created_at"]),
        pushed=_day(r.get("pushed_at") or r["created_at"]),
        description=r.get("description") or "",
        primary_language=r.get("language"),
        languages=dict(languages.get(_rest_key(r), {})),
        topics=tuple(r.get("topics") or ()),
        is_fork=bool(r.get("fork")),
    )


def from_rest(login: str, user: dict, repos: list, languages: dict, prs: Optional[int], issues: Optional[int],
              today: date, extras: list = ()) -> Snapshot:
    """Turn REST responses into a snapshot.

    languages maps "owner/name" in lower case -> {language: bytes}. extras are
    featured repositories of other owners; they do not count towards the
    user's stars. prs and issues are None when GitHub would not count them.
    """
    owned = [_repo_from_rest(r, languages) for r in repos]
    return Snapshot(
        login=user.get("login") or login,
        repos=tuple(owned + [_repo_from_rest(r, languages) for r in extras]),
        weeks=None,
        total_contributions=None,
        counters={
            "stars": sum(r.stars for r in owned),
            "prs": prs,
            "issues": issues,
            "repos": user.get("public_repos", len(owned)),
        },
        today=today,
    )


def _request(http, method: str, url: str, token: str, **kwargs):
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    kwargs.setdefault("timeout", 20)
    return http.request(method, url, headers=headers, **kwargs)


def _rate_limited(response) -> bool:
    return response.status_code in (403, 429) and "rate limit" in (response.text or "").lower()


def _fetch_rest(http, login: str, extra_repos: list, today: date) -> Snapshot:
    """The REST path, for a run without a token. It never waits for a rate limit to reset.

    Anonymous GitHub allows 60 requests an hour. The profile, the list of
    repositories and the languages of the REST_LANGUAGE_REPOS brightest ones
    are required: shares computed from part of them would be wrong, so if any
    of those calls is refused the run fails with a clear message. The
    counters (the search API has a limit of its own) and the featured
    repositories of other owners are optional: what GitHub will not give is
    left out, and said so.
    """
    limit = DataError("GitHub rate limit reached before the profile could be read. "
                      "Set GITHUB_TOKEN to raise the limit, or try again in an hour.")

    def required(url: str, **kwargs):
        response = _request(http, "GET", url, "", **kwargs)
        if _rate_limited(response):
            raise limit
        if response.status_code == 404:
            raise DataError(f"GitHub has no user '{login}'.")
        response.raise_for_status()
        return response.json()

    budget = {"open": True}

    def optional(url: str, **kwargs):
        """JSON of an optional call, or None once GitHub has started refusing."""
        if not budget["open"]:
            return None
        response = _request(http, "GET", url, "", **kwargs)
        if _rate_limited(response):
            budget["open"] = False
            logger.warning("GitHub rate limit reached at %s; going on without it. "
                           "Set GITHUB_TOKEN for complete data.", url)
            return None
        if response.status_code != 200:
            logger.warning("GET %s returned HTTP %d.", url, response.status_code)
            return None
        return response.json()

    user = required(f"{REST_URL}/users/{login}")
    repos, page = [], 1
    while True:
        items = required(f"{REST_URL}/users/{login}/repos",
                         params={"per_page": 100, "page": page, "type": "owner"})
        repos += items
        if len(items) < 100:
            break
        page += 1

    have = {_rest_key(r) for r in repos}
    extras = []
    for full_name in extra_repos:
        owner, _, name = full_name.rpartition("/")
        key = f"{owner or login}/{name}".lower()
        if key in have:
            continue
        found = optional(f"{REST_URL}/repos/{owner or login}/{name}")
        if found:
            extras.append(found)
            have.add(_rest_key(found))

    brightest = sorted((r for r in repos if not r.get("fork")),
                       key=lambda r: (-r.get("stargazers_count", 0), r["name"].lower()))[:REST_LANGUAGE_REPOS]
    languages = {}
    for repo in brightest + extras:
        url = f"{REST_URL}/repos/{repo['owner']['login']}/{repo['name']}/languages"
        response = _request(http, "GET", url, "")
        if _rate_limited(response):
            raise limit
        if response.status_code != 200:
            logger.warning("GET %s returned HTTP %d; that repository's languages are left out.",
                           url, response.status_code)
            continue
        languages[_rest_key(repo)] = response.json()

    def count(kind: str) -> Optional[int]:
        """How many pull requests or issues the user has opened; None when GitHub would not say."""
        found = optional(f"{REST_URL}/search/issues",
                         params={"q": f"author:{login} type:{kind}", "per_page": 1})
        return None if found is None else found.get("total_count", 0)

    return from_rest(login, user, repos, languages, count("pr"), count("issue"), today, extras)


def fetch(login: str, token: str, extra_repos: list, today: date, http=requests) -> Snapshot:
    """Read a profile from GitHub: one GraphQL request with a token, the REST API without one.

    With a token there is no falling back to REST when GraphQL fails: REST has
    no contribution calendar, and a poorer answer would be drawn over the
    images of the last good run. The failure is raised instead (DataError, or
    the requests exception).
    """
    if not token:
        return _fetch_rest(http, login, extra_repos, today)
    query, variables = build_query(login, extra_repos)
    response = _request(http, "POST", GRAPHQL_URL, token, json={"query": query, "variables": variables})
    response.raise_for_status()
    try:
        # a featured repository that does not exist comes back as an error next to valid data,
        # so errors alone do not disqualify the answer: a readable user does
        return from_graphql(response.json(), today, login)
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise DataError(f"GitHub's GraphQL answer could not be read ({type(error).__name__}: {error}). "
                        "Check that GITHUB_TOKEN is valid.") from error


def load_demo() -> Snapshot:
    """The fictional profile used by --demo, the README images and the tests."""
    payload = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
    return from_graphql(payload, date.fromisoformat(payload["today"]))
