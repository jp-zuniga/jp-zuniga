"""
Functions for calculating lines of code statistics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from github.GithubException import GithubException

from .consts import EMPTY_REPO_ERR
from .utils import is_user_commit

if TYPE_CHECKING:
    from github.AuthenticatedUser import AuthenticatedUser
    from github.Repository import Repository


def calc_repo_data(user: AuthenticatedUser, repo: Repository) -> tuple[int, int, int]:
    """
    Calculate a user's commits and lines of code authored across all branches.

    Args:
        user: User whose commits will be processed.
        repo: Repository to calculate data for.

    Returns:
        (int, int, int): Data calculated (additions, deletions, user commits).

    """

    additions: int = 0
    deletions: int = 0
    user_commits: int = 0

    try:
        for branch in repo.get_branches():
            try:
                for commit in set(repo.get_commits(sha=branch.name)):
                    if is_user_commit(user, commit):
                        additions += commit.stats.additions
                        deletions += commit.stats.deletions
                        user_commits += 1

            except GithubException as e:
                if e.status != EMPTY_REPO_ERR:
                    print(
                        "Error getting commits for branch "
                        f"{branch.name} in {repo.full_name}: {e!s}",
                    )

    except GithubException as e:
        if e.status != EMPTY_REPO_ERR:
            print(f"Error getting branches for {repo.full_name}: {e!s}")

    return additions, deletions, user_commits


def get_total_loc(cached_data: dict[str, dict[str, int | str]]) -> tuple[int, int, int]:
    """
    Use cached data to calculate total lines of code across all repositories.

    Args:
        cached_data: Dictionary with up-to-date cached stats.

    Return:
        (int, int, int): User's lines of code (total, additions, deletions).

    """

    adds: int = 0
    dels: int = 0

    for repo in cached_data.values():
        adds += int(repo["additions"])
        dels += int(repo["deletions"])

    return adds - dels, adds, dels
