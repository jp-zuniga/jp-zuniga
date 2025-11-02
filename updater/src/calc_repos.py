"""
Functions for calculating repository statistics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from github.AuthenticatedUser import AuthenticatedUser
    from github.PaginatedList import PaginatedList
    from github.Repository import Repository


def calc_stargazers(repos: PaginatedList[Repository]) -> int:
    """
    Iterate through the given user's owned repositories and sum their stargazers.

    Args:
        repos: User's owned repositores.

    Return:
        int: Total stargazer count across all owned repos.

    """

    return sum(repo.stargazers_count for repo in repos)


def get_affiliated_repos(user: AuthenticatedUser) -> PaginatedList[Repository]:
    """
    Get all repositories a user has write-access to.

    Args:
        user: User to get repo data for.

    Return:
        PaginatedList[Repository]: Repos user can write to.

    """

    return user.get_repos(affiliation="owner,collaborator,organization_member")


def get_owned_repos(user: AuthenticatedUser) -> PaginatedList[Repository]:
    """
    Get all repositories a user owns.

    Args:
        user: User to get repo data for.

    Return:
        PaginatedList[Repository]: User's owned repos.

    """

    return user.get_repos(type="owner")
