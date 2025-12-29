"""
Fetch a user's Github statistics and update a profile card.
"""

from .cache_man import update_cache
from .calc_commits import get_total_commits
from .calc_loc import get_total_loc
from .calc_repos import calc_stargazers, get_owned_repos
from .consts import ACCESS_TOKEN
from .svg import update_profile_cards
from .utils import calculate_age, get_verified_emails

__all__: list[str] = [
    "ACCESS_TOKEN",
    "calc_stargazers",
    "calculate_age",
    "get_owned_repos",
    "get_total_commits",
    "get_total_loc",
    "get_verified_emails",
    "update_cache",
    "update_profile_cards",
]
