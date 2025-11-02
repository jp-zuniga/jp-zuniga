"""
Functions for calculating commit statistics.
"""


def get_total_commits(cached_data: dict[str, dict[str, dict | int | str]]) -> int:
    """
    Use cached data to calculate all user-authored commits.

    Args:
        cached_data: Dictionary with up-to-date cached stats.

    Return:
        int: User's total commit count.

    """

    return sum(
        int(repo["user_commits"])  # type: ignore[reportArgumentType]
        for repo in cached_data.values()
    )
