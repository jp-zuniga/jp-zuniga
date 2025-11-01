"""
Constants used by main script.
"""

from os import environ
from pathlib import Path

EMPTY_REPO_ERR: int = 409
GH_TOKEN: str = environ["ACCESS_TOKEN"]
JUST_LENGTHS: dict[str, int] = {
    "age_dots": 44,
    "stars_dots": 45,
    "repos_dots": 45,
    "commits_dots": 43,
    "loc_total_dots": 35,
}

FILE_PATH = Path(__file__).resolve()
SVG_NAME: str = "profile_card.svg"

ROOT_DIR = FILE_PATH.parents[2]
SCRIPT_DIR = FILE_PATH.parents[1]

CACHE_DIR = Path(SCRIPT_DIR / "cache")
SVG_DIR = Path(ROOT_DIR / ".github" / "assets")
