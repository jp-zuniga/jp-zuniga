"""
Functions for handling the caching of statistics.
"""

from __future__ import annotations

from json import JSONDecodeError, dump, load
from pathlib import Path
from typing import TYPE_CHECKING

from github.GithubException import GithubException

from .calc_commits import get_branched_commits
from .calc_loc import calc_repo_data
from .calc_repos import get_affiliated_repos
from .consts import CACHE_DIR, ENCODING, USERNAME
from .utils import hash_repo

if TYPE_CHECKING:
    from github.AuthenticatedUser import AuthenticatedUser


class CacheError(Exception):
    """
    Descriptive exception for cache-handling errors.
    """


def get_cache() -> dict[str, dict[str, int | str]]:
    """
    Read a user's cached statistics.

    Return:
        dict[str, dict[str, int | str]]: Cached data.

    """

    try:
        with Path(CACHE_DIR / f"{USERNAME}.json").open(
            encoding=ENCODING,
        ) as cache:
            data: dict[str, dict[str, int | str]] = load(cache)
    except (FileNotFoundError, JSONDecodeError):
        data: dict[str, dict[str, int | str]] = {}

    return data


def update_cache(
    user: AuthenticatedUser, emails: set[str]
) -> dict[str, dict[str, int | str]]:
    """
    Update cached statistics, write them, and return them.

    Args:
        user:   User to cache stats for.
        emails: User's email to check commit authorship.

    Return:
        dict[str, dict[str, int | str]]: Updated cache.

    """

    data: dict[str, dict[str, int | str]] = get_cache()

    for repo in get_affiliated_repos(user):
        repo_hash: str = hash_repo(repo.name)
        current_commits: int = get_branched_commits(repo)

        if current_commits == 0 or (
            repo_hash in data and data[repo_hash]["commits"] == current_commits
        ):
            continue

        try:
            additions, deletions, user_commits = calc_repo_data(user, emails, repo)
        except GithubException as e:
            print(f"Error processing a repository: {e!s}")
            print("Setting its data to 0.")
            additions = deletions = user_commits = 0

        data[repo_hash] = {
            "user_commits": user_commits,
            "commits": current_commits,
            "additions": additions,
            "deletions": deletions,
        }

    write_cache(data)
    return data


def write_cache(data: dict[str, dict[str, int | str]]) -> None:
    """
    Write user's updated statistics to a cache file.

    Args:
        data: New statistics to be cached.

    """

    try:
        with Path(CACHE_DIR / f"{USERNAME}.json").open(
            encoding=ENCODING, mode="w"
        ) as cache:
            dump(data, cache, indent=2, sort_keys=False)
    except OSError as o:
        msg = f"Failed to write cache: {o!s}"
        raise CacheError(msg) from o
