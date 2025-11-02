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


def calc_repo_data(
    user: AuthenticatedUser,
    emails: set[str],
    repo: Repository,
) -> tuple[int, int, int, int]:
    """
    Calculate a user's authored data across all branches in a repository.

    Args:
        user:   User whose commits will be processed.
        emails: User's emails to check commit authorship.
        repo:   Repository to calculate data for.

    Returns:
        (int, int, int, int): Additions, deletions, user commits, and total commits.

    """

    additions: int = 0
    deletions: int = 0
    user_commits: int = 0
    processed: set[str] = set()

    for branch in repo.get_branches():
        try:
            for commit in repo.get_commits(sha=branch.name):
                sha = commit.sha
                if sha in processed:
                    continue

                processed.add(sha)

                if is_user_commit(user, emails, commit):
                    # avoid doubled api calls for individual commit stats
                    stats = commit.stats

                    additions += stats.additions
                    deletions += stats.deletions
                    user_commits += 1

        except GithubException as e:
            if e.status != EMPTY_REPO_ERR:
                print(
                    "Error getting commits for branch "
                    f"{branch.name} in {repo.full_name}: {e!s}",
                )

    return additions, deletions, user_commits, len(processed)


def get_total_loc(
    cached_data: dict[str, dict[str, dict | int | str]],
) -> tuple[int, int, int]:
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
        adds += int(repo["additions"])  # type: ignore[reportArgumentType]
        dels += int(repo["deletions"])  # type: ignore[reportArgumentType]

    return adds - dels, adds, dels
