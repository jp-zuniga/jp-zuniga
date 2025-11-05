"""
Fetch a user's Github statistics and update a profile card.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from github import Github
from github.Auth import Token

from .cache_man import update_cache
from .calc_commits import get_total_commits
from .calc_loc import get_total_loc
from .calc_repos import calc_stargazers, get_owned_repos
from .consts import ACCESS_TOKEN
from .svg import update_profile_cards
from .utils import calculate_age, get_verified_emails

if TYPE_CHECKING:
    from github.AuthenticatedUser import AuthenticatedUser
    from github.PaginatedList import PaginatedList
    from github.Repository import Repository

    from .consts import CacheDict


def main() -> None:
    """
    Execute script.
    """

    user: AuthenticatedUser = Github(auth=Token(ACCESS_TOKEN), per_page=100).get_user()  # type: ignore[reportAssignmentType]
    emails = set(get_verified_emails(user))

    cache: CacheDict = update_cache(user, emails)
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
