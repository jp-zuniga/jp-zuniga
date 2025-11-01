"""
Constants used by main script.
"""

from os import environ
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

EMPTY_REPO_ERR: int = 409
GH_TOKEN: str = environ["ACCESS_TOKEN"]
JUST_LENGTHS: dict[str, int] = {
    "age_dots": 44,
    "stars_dots": 45,
    "repos_dots": 45,
    "commits_dots": 43,
    "loc_total_dots": 35,
}

SVG_NAME: str = "profile_card.svg"

PAR_DIR = Path(__file__).resolve().parents[1]
CACHE_DIR = Path(PAR_DIR / "cache")
SVG_DIR = Path(PAR_DIR / "assets")
