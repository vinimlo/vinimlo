"""Config validation and defaults for the Galaxy Profile generator."""

import logging
import re

from generator.themes import PALETTES

logger = logging.getLogger(__name__)

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# The nine colours version 1 read from `theme`, with its defaults. A config copied from the old
# example carries all nine unchanged, so a colour equal to its default here is not an override.
LEGACY_THEME = {
    "void": "#080c14",
    "nebula": "#0f1623",
    "star_dust": "#1a2332",
    "synapse_cyan": "#00d4ff",
    "dendrite_violet": "#a78bfa",
    "axon_amber": "#ffb020",
    "text_bright": "#f1f5f9",
    "text_dim": "#94a3b8",
    "text_faint": "#64748b",
}

# theme colours that painted card backgrounds and borders; the Atlas plates have neither
RETIRED_COLOURS = ("nebula", "star_dust")

DEFAULT_METRICS = ("commits", "stars", "prs", "issues", "repos")
MAX_LANGUAGES = 20               # segments the language band can show and still be read

# theme keys that choose a palette instead of overriding a colour
PALETTE_KEYS = ("dark", "light")


def repo_key(name: str) -> str:
    """A repository's name without its owner, in lower case."""
    return str(name).split("/")[-1].lower()


def full_key(name, login: str) -> str:
    """"owner/name" in lower case for a repository as the config names it; without an owner it is the user's own."""
    owner, _, repo = str(name).strip().rpartition("/")
    return f"{owner or login}/{repo}".lower()


class ConfigError(ValueError):
    """Raised when config.yml has invalid or missing data."""


def validate_config(config: dict) -> dict:
    """Validate and apply defaults to a parsed config dict.

    Args:
        config: raw dict from yaml.safe_load()

    Returns:
        config dict with defaults applied for optional fields

    Raises:
        ConfigError: if required fields are missing or values are invalid
    """
    if not isinstance(config, dict):
        raise ConfigError("Config must be a YAML mapping (dict).")

    # username — required
    username = config.get("username")
    if not username or not isinstance(username, str) or not username.strip():
        raise ConfigError("'username' is required and must be a non-empty string.")

    # profile.name — required
    profile = config.get("profile", {})
    if not isinstance(profile, dict):
        raise ConfigError("'profile' must be a mapping.")
    if not profile.get("name"):
        raise ConfigError("'profile.name' is required.")

    # galaxy_arms — required, must be a list
    galaxy_arms = config.get("galaxy_arms", [])
    if not isinstance(galaxy_arms, list) or not galaxy_arms:
        raise ConfigError("'galaxy_arms' must be a non-empty list.")
    for i, arm in enumerate(galaxy_arms):
        if not isinstance(arm, dict):
            raise ConfigError(f"galaxy_arms[{i}] must be a mapping.")
        if not arm.get("name"):
            raise ConfigError(f"galaxy_arms[{i}].name is required.")
        if not isinstance(arm.get("items", []), list):
            raise ConfigError(f"galaxy_arms[{i}].items must be a list.")
        repos = arm.get("repos", [])
        if not isinstance(repos, list) or not all(isinstance(r, str) for r in repos):
            raise ConfigError(f"galaxy_arms[{i}].repos must be a list of repository names.")

    # a repository can be pinned to one arm only
    pinned = {}
    for i, arm in enumerate(galaxy_arms):
        for repo in arm.get("repos", []):
            key = full_key(repo, username)
            if key in pinned and pinned[key] != i:
                raise ConfigError(
                    f"repository '{key}' is listed in galaxy_arms[{pinned[key]}] and galaxy_arms[{i}]; "
                    "pick one arm."
                )
            pinned[key] = i

    # projects — optional, validate entries if present
    projects = config.get("projects")
    if projects is None:
        projects = config["projects"] = []
    if not isinstance(projects, list):
        raise ConfigError("'projects' must be a list.")
    for i, proj in enumerate(projects):
        if not isinstance(proj, dict):
            raise ConfigError(f"projects[{i}] must be a mapping.")
        if not proj.get("repo"):
            raise ConfigError(f"projects[{i}].repo is required.")
        arm_idx = proj.get("arm", 0)
        if isinstance(arm_idx, bool) or not isinstance(arm_idx, int) or arm_idx < 0 or arm_idx >= len(galaxy_arms):
            raise ConfigError(
                f"projects[{i}].arm must be an integer from 0 to {len(galaxy_arms) - 1}."
            )
        if proj.get("description") is not None and not isinstance(proj["description"], str):
            raise ConfigError(
                f"projects[{i}].description must be text; put it in quotes (got {proj['description']!r})."
            )
        key = full_key(proj["repo"], username)
        if "arm" in proj and pinned.get(key, arm_idx) != arm_idx:
            raise ConfigError(
                f"repository '{key}' is listed in galaxy_arms[{pinned[key]}].repos but projects[{i}].arm "
                f"is {arm_idx}; pick one arm."
            )

    # theme — optional, validate hex codes
    user_theme = config.get("theme", {})
    if not isinstance(user_theme, dict):
        raise ConfigError("'theme' must be a mapping.")
    palettes = {}
    overrides = {}
    for key, value in user_theme.items():
        if key in PALETTE_KEYS:
            if value not in PALETTES:
                raise ConfigError(
                    f"theme.{key} must be one of {', '.join(PALETTES)}, got '{value}'."
                )
            palettes[key] = value
        elif not isinstance(value, str) or not HEX_COLOR_RE.match(value):
            raise ConfigError(
                f"theme.{key} must be a valid hex color (e.g. #00d4ff), got '{value}'."
            )
        elif value.lower() == LEGACY_THEME.get(key, "").lower():
            # the old default, usually copied from the example config: not a customisation
            continue
        elif key in RETIRED_COLOURS:
            logger.warning("theme.%s no longer has an effect: the plates have no card backgrounds or borders.", key)
        else:
            overrides[key] = value

    config["themes"] = {
        "dark": palettes.get("dark", PALETTES[0]),
        "light": palettes.get("light", PALETTES[0]),
        "overrides": overrides,
    }

    # motion — optional flag
    motion = config.get("motion", True)
    if not isinstance(motion, bool):
        raise ConfigError(f"'motion' must be true or false, got '{motion}'.")
    config["motion"] = motion

    # Apply other defaults
    config["profile"].setdefault("tagline", "")
    config["profile"].setdefault("philosophy", "")
    config.setdefault("social", {})

    # stats and languages — optional sections; one left empty in the YAML arrives as None
    stats = _section(config, "stats")
    metrics = stats.get("metrics")
    if metrics is None:
        metrics = list(DEFAULT_METRICS)
    if not isinstance(metrics, list) or not all(isinstance(m, str) for m in metrics):
        raise ConfigError("'stats.metrics' must be a list of names, such as [stars, prs, issues].")
    stats["metrics"] = metrics

    languages = _section(config, "languages")
    exclude = languages.get("exclude")
    if exclude is None:
        exclude = []
    if not isinstance(exclude, list) or not all(isinstance(name, str) for name in exclude):
        raise ConfigError("'languages.exclude' must be a list of language names, such as [HTML, CSS].")
    languages["exclude"] = exclude
    shown = languages.get("max_display")
    if shown is None:
        shown = 8
    if isinstance(shown, bool) or not isinstance(shown, int) or shown < 1:
        raise ConfigError(f"'languages.max_display' must be a whole number of at least 1, got {shown!r}.")
    if shown > MAX_LANGUAGES:
        logger.warning("languages.max_display is %d; the band shows at most %d languages.", shown, MAX_LANGUAGES)
        shown = MAX_LANGUAGES
    languages["max_display"] = shown

    return config


def _section(config: dict, name: str) -> dict:
    """An optional section of the config as a mapping; a missing or empty one is an empty mapping."""
    section = config.get(name)
    if section is None:
        section = {}
    if not isinstance(section, dict):
        raise ConfigError(f"'{name}' must be a mapping.")
    config[name] = section
    return section
