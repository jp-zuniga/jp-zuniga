"""
General utilities used by script.
"""

from datetime import UTC, datetime

from dateutil.relativedelta import relativedelta


class CacheError(Exception):
    """
    Custom exception for cache errors.
    """


def calculate_age(bday: datetime) -> str:
    """
    Calculate time since `bday`.

    Args:
        bday: User's birthday.

    Returns:
        str: Time since user's birth.

    """

    diff = relativedelta(datetime.now(tz=UTC), bday)
    return (
        f"{diff.years} year{'s' if diff.years != 1 else ''}, "
        f"{diff.months} month{'s' if diff.months != 1 else ''}, "
        f"{diff.days} day{'s' if diff.days != 1 else ''}"
        f"{' !!!' if (diff.months == 0 and diff.days == 0) else ''}"
    )


def validate_kwargs(**kwargs: int | str) -> bool:
    """
    Validate that all necessary kwargs have been passed to a function.

    Args:
        kwargs: Keyword arguments to validate.

    Return:
        bool: `True` if all keys are present, `False` otherwise.

    """

    return all(
        key in kwargs
        for key in (
            "age",
            "stars",
            "repos",
            "commits",
            "loc_total",
            "loc_add",
            "loc_del",
        )
    )
