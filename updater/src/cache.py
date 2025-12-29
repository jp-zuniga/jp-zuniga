"""
Functions for handling the caching of statistics.
"""

from __future__ import annotations

from json import JSONDecodeError, dump, load
from typing import TYPE_CHECKING

from github.GithubException import GithubException

from .consts import CACHE_FILE, ENCODING, BranchData
from .repos import calc_repo_data, get_affiliated_repos
from .utils import hash_repo

if TYPE_CHECKING:
    from github.AuthenticatedUser import AuthenticatedUser

    from .consts import CacheDict, CachedRepo


class CacheError(Exception):
    """
    Descriptive exception for cache-handling errors.
    """


def get_cache() -> CacheDict:
    """
    Read a user's cached statistics.

    Return:
        CacheDict: Cached data.

    """

    try:
        with CACHE_FILE.open(encoding=ENCODING, mode="r") as cache:
            data: CacheDict = load(cache)
    except (FileNotFoundError, JSONDecodeError):
        data = {}

    return data


def update_cache(user: AuthenticatedUser, emails: set[str]) -> CacheDict:
    """
    Incrementally update cached statistics, write them, and return them.

    Args:
        user:   User to cache stats for.
        emails: User's verified emails to check commit authorship.

    Return:
        CacheDict: Updated cache.

    """

    data: CacheDict = get_cache()

    for repo in get_affiliated_repos(user):
        repo_hash: str = hash_repo(repo.name)
        prev: CachedRepo = data.get(repo_hash, {})
        prev_branches: BranchData = prev.get("branches", {})  # type: ignore[reportAssignmentType]

        try:
            adds_d, dels_d, user_commits_d, commits_d, new_branches = calc_repo_data(
                user=user,
                emails=emails,
                repo=repo,
                repo_hash=repo_hash,
                branches=prev_branches,
            )
        except GithubException as e:
            print(f"Error processing repository: {e!s}")
            print()
            print("Setting its deltas to 0.")
            adds_d = dels_d = user_commits_d = commits_d = 0
            new_branches = prev_branches

        # get previous totals
        prev_adds = int(prev.get("additions", 0))  # type: ignore[reportArgumentType]
        prev_dels = int(prev.get("deletions", 0))  # type: ignore[reportArgumentType]
        prev_user_commits = int(prev.get("user_commits", 0))  # type: ignore[reportArgumentType]
        prev_commits = int(prev.get("commits", 0))  # type: ignore[reportArgumentType]

        # add deltas
        data[repo_hash] = {
            "branches": new_branches,
            "additions": prev_adds + adds_d,
            "deletions": prev_dels + dels_d,
            "user_commits": prev_user_commits + user_commits_d,
            "commits": prev_commits + commits_d,
        }

    write_cache(data)
    return data


def write_cache(data: CacheDict) -> None:
    """
    Write user's updated statistics to a cache file.

    Args:
        data: New statistics to be cached.

    """

    try:
        with CACHE_FILE.open(encoding=ENCODING, mode="w") as cache:
            dump(data, cache, indent=2, sort_keys=False)
    except OSError as o:
        msg = f"Failed to write cache: {o!s}"
        raise CacheError(msg) from o
