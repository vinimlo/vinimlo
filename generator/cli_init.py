"""Interactive setup wizard for Galaxy Profile configuration."""

from __future__ import annotations

import argparse
import copy
import os
from typing import Optional

import yaml
from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.validator import EmptyInputValidator

from generator.config import (DEFAULT_METRICS, LEGACY_THEME, MAX_LANGUAGES, RETIRED_COLOURS, ConfigError,
                              validate_config)
from generator.tech_catalog import get_all_techs
from generator.themes import PALETTES

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yml")

ARMS_ASKED = 3                    # focus areas the wizard asks for; an existing config may hold more, and keeps them
UNREADABLE = object()             # an existing config.yml that is not valid YAML
PROFILE_EXTRAS = ("bio", "company", "location", "philosophy")
PALETTE_NOTES = {
    "deep-sky": "deep-sky: a night sky, stars in their real colours",
    "cyanotype": "cyanotype: Prussian blue and paper white, one warm accent",
}
METRIC_NAMES = {"commits": "Commits", "stars": "Stars", "prs": "PRs", "issues": "Issues", "repos": "Repos"}


def _mapping(value) -> dict:
    """A section of an existing config, or nothing if it is not a mapping."""
    return value if isinstance(value, dict) else {}


def _text(value) -> str:
    """A default for a text prompt: the prompt library only takes strings."""
    return "" if value is None else str(value)


def run_init():
    """Orchestrate the full interactive setup wizard."""
    print("\n🌌 Galaxy Profile — Interactive Setup\n")

    existing = _detect_existing_config()
    defaults = {}

    if existing is UNREADABLE:
        replace = inquirer.confirm(
            message="config.yml exists but could not be read as YAML. Replace it?",
            default=False,
        ).execute()
        if not replace:
            print("Setup cancelled. config.yml was left as it is.")
            return
    elif existing is not None:
        action, defaults = _handle_existing_config(existing)
        if action == "cancel":
            print("Setup cancelled.")
            return

    essential = _prompt_essential(defaults)
    arms = _prompt_galaxy_arms(defaults)
    look = _prompt_look(defaults)

    configure_advanced = inquirer.confirm(
        message="Configure advanced options (bio, social, projects, stats, languages)?",
        default=False,
    ).execute()

    advanced = _prompt_advanced(defaults, arms) if configure_advanced else {}

    config = _build_config(essential, arms, advanced, look, defaults)
    path = _save_config(config)

    # Validate
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        validate_config(raw)
        print(f"\n✅ Config saved and validated: {path}")
    except ConfigError as e:
        print(f"\n⚠️  Config saved to {path} but validation found issues: {e}")

    _offer_generation()


def _detect_existing_config():
    """The parsed config.yml if there is one, None if there is none, UNREADABLE if it cannot be parsed."""
    path = os.path.normpath(_CONFIG_PATH)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (yaml.YAMLError, UnicodeDecodeError, OSError):
        return UNREADABLE


def _handle_existing_config(existing) -> tuple[str, dict]:
    """Ask user what to do with existing config. Return (action, defaults)."""
    action = inquirer.select(
        message="config.yml already exists. What would you like to do?",
        choices=[
            {"name": "Overwrite — start from scratch", "value": "overwrite"},
            {"name": "Edit — use current values as defaults, keep the rest", "value": "edit"},
            {"name": "Cancel", "value": "cancel"},
        ],
    ).execute()

    if action == "cancel":
        return ("cancel", {})
    if action == "edit":
        return ("edit", _mapping(existing))
    return ("overwrite", {})


def _prompt_essential(defaults: dict) -> dict:
    """Collect essential fields: username, name, tagline."""
    profile_defaults = _mapping(defaults.get("profile"))

    username = inquirer.text(
        message="GitHub username:",
        default=_text(defaults.get("username")),
        validate=EmptyInputValidator("Username cannot be empty."),
    ).execute()

    name = inquirer.text(
        message="Display name:",
        default=_text(profile_defaults.get("name")),
        validate=EmptyInputValidator("Name cannot be empty."),
    ).execute()

    tagline = inquirer.text(
        message="Tagline (short description):",
        default=_text(profile_defaults.get("tagline")),
    ).execute()

    return {"username": username, "name": name, "tagline": tagline}


def _arm_entry(name: str, items: list, previous: dict) -> dict:
    """One focus area as it goes into the config. Repositories pinned to it before are kept."""
    entry = {"name": name, "items": list(items)}
    if isinstance(previous, dict) and previous.get("repos"):
        entry["repos"] = list(previous["repos"])
    return entry


def _tech_choices(catalogue: list, chosen: list) -> list:
    """The technologies to pick from, those the area already lists first and already selected.

    An item that is not in the catalogue (a custom one) is offered too, so
    editing a config does not lose it.
    """
    chosen = [str(item) for item in chosen if item is not None and str(item).strip()]
    rest = [tech for tech in catalogue if tech not in chosen]
    return [Choice(item, enabled=True) for item in chosen] + [Choice(tech) for tech in rest]


def _existing_arms(defaults: dict) -> list:
    arms = defaults.get("galaxy_arms")
    return [arm for arm in arms if isinstance(arm, dict)] if isinstance(arms, list) else []


def _prompt_galaxy_arms(defaults: dict) -> list:
    """Collect three galaxy arms, each with a name and its technologies; further existing arms are kept."""
    all_techs = get_all_techs()
    default_arms = _existing_arms(defaults)
    arms = []

    for i in range(ARMS_ASKED):
        print(f"\n--- Galaxy Arm {i + 1}/{ARMS_ASKED} ---")
        arm_default = default_arms[i] if i < len(default_arms) else {}

        arm_name = inquirer.text(
            message=f"Arm {i + 1} name (e.g. Frontend, Backend, DevOps):",
            default=_text(arm_default.get("name")),
            validate=EmptyInputValidator("Arm name cannot be empty."),
        ).execute()

        items = arm_default.get("items")
        arm_techs = inquirer.fuzzy(
            message=f"Arm {i + 1} technologies (type to filter, space to select):",
            choices=_tech_choices(all_techs, items if isinstance(items, list) else []),
            multiselect=True,
            validate=lambda result: len(result) > 0,
            invalid_message="Select at least one technology.",
        ).execute()

        arms.append(_arm_entry(arm_name, arm_techs, arm_default))

    if len(default_arms) > ARMS_ASKED:
        kept = default_arms[ARMS_ASKED:]
        print(f"\nKeeping your other {len(kept)} focus area(s) as they are: "
              + ", ".join(_text(arm.get("name")) for arm in kept))
        arms += [copy.deepcopy(arm) for arm in kept]

    return arms


def _theme_section(dark: str, light: str, previous) -> dict:
    """The config's `theme`: the two palettes, plus any version-1 colour the user had really changed.

    A colour equal to its old default is not written again, and the two that
    no longer paint anything (card backgrounds and borders) are dropped.
    """
    section = {"dark": dark, "light": light}
    if isinstance(previous, dict):
        for key, default in LEGACY_THEME.items():
            value = previous.get(key)
            if key in RETIRED_COLOURS or not isinstance(value, str) or value.lower() == default.lower():
                continue
            section[key] = value
    return section


def _prompt_look(defaults: dict) -> dict:
    """Ask for the palette of each mode and whether the images move."""
    print("\n--- Look ---")
    previous = defaults.get("theme")
    chosen = _mapping(previous)

    def palette(mode: str) -> str:
        return chosen.get(mode) if chosen.get(mode) in PALETTES else PALETTES[0]

    palettes = [{"name": PALETTE_NOTES[name], "value": name} for name in PALETTES]
    dark = inquirer.select(
        message="Palette for GitHub's dark theme:",
        choices=palettes,
        default=palette("dark"),
    ).execute()
    light = inquirer.select(
        message="Palette for GitHub's light theme:",
        choices=palettes,
        default=palette("light"),
    ).execute()
    motion = inquirer.confirm(
        message="Animate the images? (visitors who ask their system for reduced motion always get them still)",
        default=defaults.get("motion", True) is not False,
    ).execute()
    kept = _theme_section(dark, light, previous)
    return {"dark": dark, "light": light, "motion": motion,
            "colours": {key: value for key, value in kept.items() if key not in ("dark", "light")}}


def _whole(text, fallback: int, most: int) -> int:
    """A whole number from 1 to `most` typed at a prompt, or the fallback if it is anything else."""
    text = str(text).strip()
    if text.isascii() and text.isdigit() and int(text) >= 1:
        return min(int(text), most)
    return fallback


def _prompt_advanced(defaults: dict, arms: list) -> dict:
    """Collect the optional sections. Every key asked for is in the result; an empty answer removes it."""
    result = {}
    profile_defaults = _mapping(defaults.get("profile"))
    social_defaults = _mapping(defaults.get("social"))

    # Bio, company, location, philosophy
    profile_fields = [
        ("bio", "Bio (multi-line, use \\n for newlines):"),
        ("company", "Company:"),
        ("location", "Location:"),
        ("philosophy", "Philosophy quote:"),
    ]
    for key, prompt in profile_fields:
        default = _text(profile_defaults.get(key))
        if key == "bio":
            default = default.strip().replace("\n", "\\n")
        value = inquirer.text(message=prompt, default=default).execute()
        result[key] = value.replace("\\n", "\n") if key == "bio" else value

    # Social links
    print("\n--- Social Links (leave blank to skip) ---")
    social_fields = [("email", "Email:"), ("linkedin", "LinkedIn username:"), ("website", "Website URL:")]
    social = {}
    for key, prompt in social_fields:
        value = inquirer.text(
            message=prompt,
            default=_text(social_defaults.get(key)),
        ).execute()
        if value:
            social[key] = value
    result["social"] = social

    # Projects
    result["projects"] = _prompt_projects(defaults, arms)

    # Stats
    previous = _mapping(defaults.get("stats")).get("metrics")
    shown = previous if isinstance(previous, list) else list(DEFAULT_METRICS)
    metrics = inquirer.checkbox(
        message="Which stats metrics to display?",
        choices=[Choice(key, name=name, enabled=key in shown) for key, name in METRIC_NAMES.items()],
    ).execute()
    result["stats"] = {"metrics": metrics} if metrics else {}

    # Languages
    print("\n--- Language Display Settings ---")
    language_defaults = _mapping(defaults.get("languages"))
    excluded = language_defaults.get("exclude")
    exclude_input = inquirer.text(
        message="Languages to exclude (comma-separated, e.g. HTML,CSS,Shell):",
        default=",".join(str(name) for name in excluded) if isinstance(excluded, list) else "",
    ).execute()
    exclude = [lang.strip() for lang in exclude_input.split(",") if lang.strip()]

    max_display = inquirer.text(
        message=f"Max languages to display (1 to {MAX_LANGUAGES}):",
        default=str(_whole(language_defaults.get("max_display"), 8, MAX_LANGUAGES)),
    ).execute()
    result["languages"] = {"exclude": exclude, "max_display": _whole(max_display, 8, MAX_LANGUAGES)}

    return result


def _project_entry(repo: str, arm: Optional[int], description: str) -> dict:
    """One featured project as it goes into the config. Without an arm, its languages decide where it sits."""
    entry = {"repo": repo}
    if arm is not None:
        entry["arm"] = arm
    entry["description"] = description
    return entry


def _prompt_projects(defaults: dict, arms: list) -> list:
    """Collect featured projects in a loop. A project may be placed on any of the arms being written."""
    previous = defaults.get("projects")
    default_projects = [p for p in previous if isinstance(p, dict) and p.get("repo")] if isinstance(previous, list) else []
    projects = []

    add_project = inquirer.confirm(
        message="Add a featured project?",
        default=len(default_projects) > 0,
    ).execute()

    places = [Choice(None, name="Let its languages decide")]
    places += [Choice(index, name=f"Arm {index + 1}: {_text(arm.get('name'))}") for index, arm in enumerate(arms)]

    idx = 0
    while add_project:
        proj_default = default_projects[idx] if idx < len(default_projects) else {}

        repo = inquirer.text(
            message="Repository (owner/repo):",
            default=_text(proj_default.get("repo")),
            validate=EmptyInputValidator("Repository cannot be empty."),
        ).execute()

        pinned = proj_default.get("arm")
        in_range = isinstance(pinned, int) and not isinstance(pinned, bool) and 0 <= pinned < len(arms)
        arm = inquirer.select(
            message="Which arm of the galaxy does it sit on?",
            choices=places,
            default=pinned if in_range else None,
        ).execute()

        description = inquirer.text(
            message="Short description:",
            default=_text(proj_default.get("description")),
        ).execute()

        projects.append(_project_entry(repo, arm, description))
        idx += 1

        add_project = inquirer.confirm(
            message="Add another project?",
            default=idx < len(default_projects),
        ).execute()

    return projects


def _build_config(essential: dict, arms: list, advanced: dict, look: Optional[dict] = None,
                  existing: Optional[dict] = None) -> dict:
    """Assemble the final config dictionary.

    look is what _prompt_look returns. existing is the config being edited:
    everything in it that the wizard did not ask about is kept as it was. In
    advanced, an empty value removes its key.
    """
    kept = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    profile = dict(_mapping(kept.get("profile")))
    profile["name"] = essential["name"]
    profile["tagline"] = essential.get("tagline", "")
    asked = {"username": essential["username"], "profile": profile, "galaxy_arms": arms}
    config = {**asked, **{key: value for key, value in kept.items() if key not in asked}}

    for key in PROFILE_EXTRAS:
        if key in advanced:
            if advanced[key]:
                profile[key] = advanced[key]
            else:
                profile.pop(key, None)

    for key in ("social", "projects", "stats", "languages"):
        if key in advanced:
            if advanced[key]:
                config[key] = advanced[key]
            else:
                config.pop(key, None)

    if look:
        config["theme"] = {"dark": look["dark"], "light": look["light"], **look.get("colours", {})}
        config["motion"] = look["motion"]

    return config


def _save_config(config: dict) -> str:
    """Serialize config to YAML and write to config.yml. Return the path."""
    path = os.path.normpath(_CONFIG_PATH)

    header = (
        "# Galaxy Profile README Configuration\n"
        "# Generated by: python -m generator.main init\n"
        "#\n"
        "# Regenerate SVGs with:\n"
        "#   python -m generator.main\n"
        "#\n"
        "# Demo mode (no API calls):\n"
        "#   python -m generator.main --demo\n\n"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return path


def _offer_generation():
    """Ask if user wants to generate SVGs now."""
    generate_now = inquirer.confirm(
        message="Generate SVGs now?",
        default=True,
    ).execute()

    if generate_now:
        print("\nGenerating SVGs...")
        from generator.main import generate

        generate(argparse.Namespace(demo=False))
