"""
Functions for calculating lines of code statistics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .utils import from_iso_z, hash_branch, is_user_commit, to_iso_z

if TYPE_CHECKING:
    from datetime import datetime

    from github.AuthenticatedUser import AuthenticatedUser
    from github.Repository import Repository

    from .consts import BranchData, CacheDict, RepoData


def calc_repo_data(
    user: AuthenticatedUser,
    emails: set[str],
    repo: Repository,
    repo_hash: str,
    branches: BranchData,
) -> RepoData:
    """
    Incrementally calculate the user's authored data for a repository.

    Walk only commits that are new since the last run, per branch,
    and dedupe SHAs across branches to avoid double-counting merges.

    Args:
        user:      User whose commits will be processed.
        emails:    User's emails to check commit authorship.
        repo:      Repository to calculate data for.
        repo_hash: Hashed repository name.
        branches:  Cached branch data (head SHA and last-seen date).

    Returns:
        RepoData: Tuple containing: new additions, new deletions,
                                    new user commits, new total commits,
                                    new branch data.

    Raises:
        GithubException: When something goes unavoidably wrong (request time-out).
                         Callers are responsible for catching these,
                         because handling the exceptions here would
                         lead to illegal levels of indentation.

    """

    additions_d: int = 0
    deletions_d: int = 0
    user_commits_d: int = 0
    commits_d: int = 0

    processed: set[str] = set()

    for branch in repo.get_branches():
        hashed_branch = hash_branch(branch.name, repo_hash)
        prev_branches: dict[str, str] = branches.get(hashed_branch, {})
        prev_head = prev_branches.get("head", "")
        last_seen = prev_branches.get("last_seen", "")
        head_sha = branch.commit.sha

        if prev_head == head_sha:
            continue

        kwargs: dict[str, datetime] = {}
        if last_seen != "":
            kwargs["since"] = from_iso_z(last_seen)

        for commit in repo.get_commits(sha=branch.name, **kwargs):  # type: ignore[reportArgumentType]
            sha = commit.sha

            if sha == prev_head:
                break
            if sha in processed:
                continue

            processed.add(sha)
            commits_d += 1

            if is_user_commit(user, emails, commit):
                stats = commit.stats
                additions_d += stats.additions
                deletions_d += stats.deletions
                user_commits_d += 1

        # safety first even if it means an absolutely degenerate get
        head_date: datetime | None = getattr(  # type: ignore[reportAssignmentType]
            getattr(getattr(branch.commit, "commit", None), "committer", None),
            "date",
            None,
        )

        branches[hashed_branch] = {
            "head": head_sha,
            "last_seen": to_iso_z(head_date),
        }

    return additions_d, deletions_d, user_commits_d, commits_d, branches


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
