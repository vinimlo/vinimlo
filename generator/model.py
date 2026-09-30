"""View models: turn a data snapshot and the config into what each plate draws."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from generator.config import full_key, repo_key
from generator.data import Repo, Snapshot

# An arm lists technologies by the name people use; GitHub reports languages by another.
ALIASES = {"docker": "dockerfile", "vue.js": "vue", "node.js": "javascript"}
MIN_SHARE = 0.15          # a repository joins an arm when its languages are at least this much of its code
STAR_LIMIT = 48           # repositories drawn in the galaxy
LABEL_LIMIT = 4           # stars that get their name written next to them
FEATURED_LIMIT = 3
NOW_DAYS, YEAR_DAYS = 30, 365


def recency(pushed: date, today: date) -> str:
    """How alive a repository is: "now" (a month), "year", or "dorm"."""
    days = (today - pushed).days
    if days <= NOW_DAYS:
        return "now"
    return "year" if days <= YEAR_DAYS else "dorm"


def _tech(name: str) -> str:
    key = str(name).strip().lower()
    return ALIASES.get(key, key)


def _featured_keys(config: dict, login: str) -> set:
    return {full_key(p["repo"], login) for p in config.get("projects", [])}


def visible_repos(snap: Snapshot, config: dict, limit: int = STAR_LIMIT) -> list:
    """The repositories that become stars, featured ones first.

    Forks are left out unless the user features one, and so is the profile
    repository: the workflow that regenerates these images keeps it "active".
    """
    login = snap.login.lower()
    wanted = _featured_keys(config, login)
    repos = [r for r in snap.repos
             if (not r.is_fork or r.key in wanted)
             and not (r.owner.lower() == login and r.name.lower() == login)]
    repos.sort(key=lambda r: (r.key not in wanted, -r.stars, -r.pushed.toordinal(), r.key))
    return repos[:limit]


def _share_arm(repo: Repo, arm_techs: list) -> Optional[int]:
    total = sum(repo.languages.values())
    if total:
        shares = {_tech(lang): size / total for lang, size in repo.languages.items()}
    elif repo.primary_language:
        shares = {_tech(repo.primary_language): 1.0}      # REST gave no byte counts
    else:
        return None
    scores = [sum(share for lang, share in shares.items() if lang in techs) for techs in arm_techs]
    best = max(scores, default=0.0)
    return scores.index(best) if best >= MIN_SHARE else None


def _meant(entry, repos: list, login: str) -> str:
    """The key of the repository a pin names, among `repos`."""
    full = full_key(entry, login)
    if "/" in str(entry):
        return full
    same_name = [repo.key for repo in repos if repo.name.lower() == repo_key(entry)]
    return same_name[0] if len(same_name) == 1 else full


def unmatched(snap: Snapshot, config: dict) -> tuple:
    """(featured projects GitHub did not return, pins that name no star), as the config writes them.

    Nothing here stops a run; it is what the user should be told, because a
    misspelt name otherwise just has no effect.
    """
    known = {repo.key for repo in snap.repos}
    missing = [str(p["repo"]) for p in config.get("projects", []) if full_key(p["repo"], snap.login) not in known]
    repos = visible_repos(snap, config)
    drawn = {repo.key for repo in repos}
    pins = [str(name) for arm in config.get("galaxy_arms", []) for name in arm.get("repos", [])
            if _meant(name, repos, snap.login) not in drawn]
    return missing, pins


def assign_arms(repos: list, arms: list, projects: list, login: str = "") -> dict:
    """{repository key: arm index or None}: explicit pins first, then share of code.

    A pin names a repository as "owner/name" or by its name alone. A name
    alone is the user's own repository, or, if they have none by that name,
    the only other one that has it.
    """
    def meant(entry) -> str:
        return _meant(entry, repos, login)

    pinned = {}
    for project in projects:
        if "arm" in project:
            pinned[meant(project["repo"])] = project["arm"]
    for index, arm in enumerate(arms):
        for name in arm.get("repos", []):
            pinned[meant(name)] = index
    arm_techs = [{_tech(item) for item in arm.get("items", [])} for arm in arms]
    return {repo.key: pinned[repo.key] if repo.key in pinned else _share_arm(repo, arm_techs) for repo in repos}


@dataclass(frozen=True)
class Featured:
    name: str
    description: str
    language: Optional[str]
    stars: int
    pushed: date
    state: str


def featured(snap: Snapshot, config: dict) -> list:
    """Up to three featured projects, brightest first."""
    by_key = {r.key: r for r in snap.repos}
    items, seen = [], set()
    for project in config.get("projects", []):
        key = full_key(project["repo"], snap.login)
        repo = by_key.get(key)
        if repo is None or key in seen:
            continue
        seen.add(key)
        items.append(Featured(
            name=repo.name,
            description=project.get("description") or repo.description,
            language=repo.primary_language,
            stars=repo.stars,
            pushed=repo.pushed,
            state=recency(repo.pushed, snap.today),
        ))
    items.sort(key=lambda f: -f.stars)
    return items[:FEATURED_LIMIT]


def language_shares(snap: Snapshot, exclude: list, max_display: int) -> list:
    """(language, percent) for the user's own non-fork repositories, largest first.

    The profile repository is left out: it holds this generator's code, which
    says nothing about what the user writes. A language too small to round to
    a tenth of a percent is left out too.
    """
    login, skip, totals = snap.login.lower(), {str(name).lower() for name in exclude}, {}
    for repo in snap.repos:
        if repo.is_fork or repo.owner.lower() != login or repo.name.lower() == login:
            continue
        for lang, size in repo.languages.items():
            if lang.lower() not in skip:
                totals[lang] = totals.get(lang, 0) + size
    whole = sum(totals.values())
    if not whole:
        return []
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))[:max_display]
    shares = [(lang, round(size / whole * 100, 1)) for lang, size in ranked]
    return [(lang, percent) for lang, percent in shares if percent > 0]


def weekly_series(snap: Snapshot) -> Optional[tuple]:
    """(values, first days, total, index of the peak week), or None without a calendar."""
    if not snap.weeks:
        return None
    dates = [day for day, _count in snap.weeks]
    values = [count for _day, count in snap.weeks]
    total = snap.total_contributions if snap.total_contributions is not None else sum(values)
    return values, dates, total, values.index(max(values))


@dataclass(frozen=True)
class Arm:
    name: Optional[str]       # None for the unnamed arms of a galaxy with no matched repository
    repos: tuple              # Repo, oldest first


@dataclass(frozen=True)
class GalaxyModel:
    arms: tuple               # Arm, in config order; only focus areas that have repositories
    loose: tuple              # Repo on no arm
    labels: frozenset         # keys (Repo.key) of the repositories that get a label
    order: tuple              # every drawn repository's key, oldest first (the entrance order)
    today: Optional[date] = None   # the day a star's state is judged against


def galaxy(snap: Snapshot, config: dict) -> GalaxyModel:
    """What the galaxy is made of: which arms exist, which star sits on which, and who is named."""
    repos = visible_repos(snap, config)
    arms_config = config.get("galaxy_arms", [])
    assigned = assign_arms(repos, arms_config, config.get("projects", []), snap.login)

    def oldest_first(items):
        return tuple(sorted(items, key=lambda r: (r.created, r.key)))

    arms = tuple(
        Arm(arm["name"], oldest_first(r for r in repos if assigned[r.key] == index))
        for index, arm in enumerate(arms_config)
        if any(assigned[r.key] == index for r in repos)
    )
    on_arm = {r.key for arm in arms for r in arm.repos}
    wanted = _featured_keys(config, snap.login)
    named = [r.key for r in repos if r.key in wanted]
    if repos:
        brightest = max(repos, key=lambda r: (r.stars, r.pushed)).key
        if brightest not in named:
            named.append(brightest)
    return GalaxyModel(
        arms=arms or (Arm(None, ()), Arm(None, ())),
        loose=oldest_first(r for r in repos if r.key not in on_arm),
        labels=frozenset(named[:LABEL_LIMIT]),
        order=tuple(r.key for r in oldest_first(repos)),
        today=snap.today,
    )

