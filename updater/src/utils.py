"""
General utilities used by the script.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from hmac import new as new_hash
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta
from github.GithubException import GithubException

from .consts import ENCODING, HASH_KEY

if TYPE_CHECKING:
    from github.AuthenticatedUser import AuthenticatedUser
    from github.Commit import Commit
    from github.Repository import Repository


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


def from_iso_z(s: str) -> datetime:
    """
    Parse an ISO8601 Z string back into a UTC-aware datetime.

    Args:
        s: String to be converted to a `datetime` object.

    Return:
        datetime: Object corresponding to IS8601 Z string.

    """

    return datetime.fromisoformat(s).astimezone(UTC)


def get_branch_heads(repo: Repository) -> dict[str, str]:
    """
    Fetch the heads of all the branches in the given repository.

    Args:
        repo: Repository whose branch heads will be fetched.

    Return:
        dict[str, str]: Mapping of branches and branch heads.

    """

    return {branch.name: branch.commit.sha for branch in repo.get_branches()}


def get_verified_emails(user: AuthenticatedUser) -> set[str]:
    """
    Fetch all verified email addresses for the given user.

    Returns:
        list[str]: User's verified emails.

    """

    try:
        return {
            email_info.email.lower()
            for email_info in user.get_emails()
            if email_info.verified
        }
    except GithubException as g:
        print(f"Warning: Could not fetch verified emails: {g!s}")
        return set()


def hash_branch(branch_name: str, repo_hash: str) -> str:
    """
    Create a keyed hash from a branch, salted by its repository's hash.

    Args:
        branch_name: Branch to hash.
        repo_hash:   Hashed repository name to use as salt.

    Return:
        str: Keyed `hmac` hash.

    """

    return new_hash(
        HASH_KEY,
        f"{repo_hash}:{branch_name}".encode(ENCODING),
        sha256,
    ).hexdigest()


def hash_repo(name: str) -> str:
    """
    Create a keyed hash from a repository name.

    Args:
        name: Repo name to hash.

    Return:
        str: Keyed `hmac` hash.

    """

    return new_hash(HASH_KEY, name.encode(ENCODING), sha256).hexdigest()


def is_user_commit(user: AuthenticatedUser, emails: set[str], commit: Commit) -> bool:
    """
    Check if commit belongs to defined user.

    Args:
        commit: Commit to check.
        user:   User to check.
        emails: User's verified emails.

    Returns:
        bool: If the commit was authored by the user.

    """

    if commit.author and commit.author.id == user.id:
        return True

    if commit.commit and commit.commit.author:
        commit_email: str = (
            commit.commit.author.email.lower() if commit.commit.author.email else ""
        )

        if commit_email in emails:
            return True

    return bool(commit.author and commit.author.login == user.login)


def to_iso_z(dt: datetime | None = None) -> str:
    """
    Serialize a datetime to an ISO8601 Z string.

    Args:
        dt: `datetime` object to be converted to a string.
            Defaults to current UTC time if not provided.

    Return:
        str: ISO8601 Z string corresponding to `datetime` given.

    """

    if dt is None:
        dt = datetime.now(tz=UTC)

    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def validate_kwargs(**kwargs: int | str) -> bool:
    """
    Validate that all necessary kwargs have been passed to a function.

    Args:
        kwargs: Keyword arguments to validate.

    Return:
        bool: `True` if all keys are present, `False` otherwise.

    """

    return all(
        key in kwargs and isinstance(kwargs[key], str if key == "age" else int)
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
