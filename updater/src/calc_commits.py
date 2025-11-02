"""
Functions for calculating commit statistics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from github.GithubException import GithubException

from .consts import EMPTY_REPO_ERR

if TYPE_CHECKING:
    from github.Repository import Repository


def get_branched_commits(repo: Repository) -> int:
    """
    Get total commit count across all branches of the given repository.

    Args:
        repo: Repository to get commit count for.

    Returns:
        int: Total commit count in given repository.

    """

    processed_commits: set[str] = set()

    try:
        for branch in repo.get_branches():
            try:
                for commit in repo.get_commits(sha=branch.name):
                    processed_commits.add(commit.sha)

            except GithubException as e:
                if e.status != EMPTY_REPO_ERR:
                    print(
                        "Error getting commits for branch "
                        f"`{branch.name}` in `{repo.full_name}`: {e!s}",
                    )

    except GithubException as e:
        if e.status != EMPTY_REPO_ERR:
            print(f"Error getting branches for {repo.full_name}: {e!s}")

    return len(processed_commits)


def get_total_commits(cached_data: dict[str, dict[str, int | str]]) -> int:
    """
    Use cached data to calculate all user-authored commits.

    Args:
        cached_data: Dictionary with up-to-date cached stats.

    Return:
        int: User's total commit count.

    """

    return sum(int(repo["user_commits"]) for repo in cached_data.values())
