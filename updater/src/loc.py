"""
Functions for calculating lines of code statistics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .consts import CacheDict


def get_total_loc(
    cached_data: CacheDict,
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
        adds += int(repo.get("additions", 0))  # type: ignore[reportArgumentType]
        dels += int(repo.get("deletions", 0))  # type: ignore[reportArgumentType]

    return adds - dels, adds, dels
