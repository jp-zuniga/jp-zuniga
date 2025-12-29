"""
Constants used by the script.
"""

from __future__ import annotations

from hashlib import sha256
from os import environ
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BranchData = dict[str, dict[str, str]]
CachedRepo = dict[str, int | BranchData]
CacheDict = dict[str, CachedRepo]
RepoData = tuple[int, int, int, int, BranchData]

ENCODING: str = "utf-8"
ACCESS_TOKEN: str = environ["ACCESS_TOKEN"]
HASH_KEY: bytes = environ["HASH_KEY"].encode(ENCODING)
USERNAME: str = sha256(environ["USERNAME"].encode(ENCODING)).hexdigest()[:10]

EMPTY_REPO_ERR: int = 409
JUST_LENGTHS: dict[str, int] = {
    "age_dots": 44,
    "stars_dots": 45,
    "repos_dots": 45,
    "commits_dots": 43,
    "loc_total_dots": 37,
}

FILE_PATH: Path = Path(__file__).resolve()
ROOT_DIR: Path = FILE_PATH.parents[2]
SRC_DIR: Path = FILE_PATH.parent

CACHE_DIR: Path = Path(SRC_DIR / "cache")
CACHE_DIR.mkdir(exist_ok=True)

CACHE_FILE: Path = Path(CACHE_DIR / f"{USERNAME}.json")

SVG_DIR: Path = Path(ROOT_DIR / ".github" / "assets")
SVG_DIR.mkdir(exist_ok=True)
