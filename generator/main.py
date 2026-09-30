"""Entry point for the Galaxy Profile README generator."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests
import yaml

from generator import build, data, model
from generator.config import ConfigError, full_key, validate_config

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = Path("assets") / "generated"


def run(config_path, out_dir, demo: bool, token: str, today: date, http=requests) -> list:
    """Read the config, get the profile's data, draw every plate and write the files.

    Returns the paths written. Everything is drawn before anything is written,
    so a failure (ConfigError, data.DataError, a network error) leaves the
    images of the last good run untouched.
    """
    try:
        with open(config_path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise ConfigError(f"the config file could not be read as YAML: {error}") from error
    config = validate_config(raw)

    if demo:
        snap = data.load_demo()
    else:
        featured = {}                                    # each featured project once, as first written
        for project in config["projects"]:
            featured.setdefault(full_key(project["repo"], config["username"]), str(project["repo"]).strip())
        snap = data.fetch(config["username"], token, list(featured.values()), today, http=http)
        missing, pins = model.unmatched(snap, config)
        for name in missing:
            logger.warning("Featured project '%s' was not found on GitHub; it is left out.", name)
        for name in pins:
            logger.warning("galaxy_arms lists the repository '%s', which is not one of the stars drawn; "
                           "check its spelling.", name)
    files = build.render_all(config, snap)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, svg in files.items():
        path = out_dir / name
        path.write_text(svg, encoding="utf-8")
        written.append(path)
    return written


def generate(args) -> None:
    """The `generate` command: config.yml (or the example, in demo mode) into assets/generated."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    demo = getattr(args, "demo", False)
    config_path = ROOT / ("config.example.yml" if demo else "config.yml")
    if not config_path.exists():
        if demo:
            logger.error("config.example.yml not found.")
        else:
            logger.error("config.yml not found. Copy config.example.yml to config.yml and edit it.")
        sys.exit(1)

    if demo:
        logger.info("Demo mode: sample data, no calls to GitHub.")
    try:
        written = run(config_path, ROOT / OUTPUT, demo, os.environ.get("GITHUB_TOKEN", ""),
                      datetime.now(timezone.utc).date())
    except ConfigError as error:
        logger.error("Invalid config: %s", error)
        sys.exit(1)
    except (data.DataError, requests.exceptions.RequestException) as error:
        logger.error("Could not read the profile from GitHub: %s. The existing images were left as they were.", error)
        sys.exit(1)
    logger.info("Done: %d SVGs written to %s.", len(written), ROOT / OUTPUT)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Generate Galaxy Profile SVGs")
    subparsers = parser.add_subparsers(dest="command")

    # Subcommand: init
    subparsers.add_parser("init", help="Interactive setup wizard to create config.yml")

    # Subcommand: generate
    gen_parser = subparsers.add_parser("generate", help="Generate SVGs from config")
    gen_parser.add_argument(
        "--demo",
        action="store_true",
        default=argparse.SUPPRESS,       # so `--demo generate` keeps the flag given before the subcommand
        help="Generate SVGs with demo data (no API calls, uses config.example.yml)",
    )

    # Top-level --demo for backward compatibility (python -m generator.main --demo)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Generate SVGs with demo data (no API calls, uses config.example.yml)",
    )

    args = parser.parse_args(argv)

    if args.command == "init":
        from generator.cli_init import run_init
        run_init()
    else:
        # Default behavior: generate (supports both `generate --demo` and `--demo`)
        generate(args)


if __name__ == "__main__":
    main()
