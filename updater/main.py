"""
Main entry point for script execution.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from github import Github
from github.Auth import Token

from src import (
    ACCESS_TOKEN,
    calc_stargazers,
    calculate_age,
    get_owned_repos,
    get_total_commits,
    get_total_loc,
    get_verified_emails,
    update_cache,
    update_profile_cards,
)

if TYPE_CHECKING:
    from github.AuthenticatedUser import AuthenticatedUser
    from github.PaginatedList import PaginatedList
    from github.Repository import Repository

    from src.consts import CacheDict


def main() -> None:
    """
    Execute script.
    """

    user: AuthenticatedUser = Github(  # type: ignore[reportAssignmentType]
        auth=Token(token=ACCESS_TOKEN), per_page=100
    ).get_user()

    cache: CacheDict = update_cache(user=user, emails=get_verified_emails(user))

    owned_repos: PaginatedList[Repository] = get_owned_repos(user)

    age_str: str = calculate_age(datetime(2005, 7, 7, tzinfo=UTC))
    star_count: int = calc_stargazers(owned_repos)
    commit_count: int = get_total_commits(cache)

    loc_total, loc_add, loc_del = get_total_loc(cache)

    update_profile_cards(
        age=age_str,
        stars=star_count,
        repos=owned_repos.totalCount,
        commits=commit_count,
        loc_total=loc_total,
        loc_add=loc_add,
        loc_del=loc_del,
    )


if __name__ == "__main__":
    main()
