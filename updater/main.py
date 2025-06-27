from datetime import datetime
from hashlib import sha256
from json import JSONDecodeError, dump, load
from os import environ
from pathlib import Path
from sys import exit, stderr
from typing import Any

from dateutil.relativedelta import relativedelta
from github import Github, GithubException
from github.Auth import Token
from github.Commit import Commit
from github.Repository import PaginatedList, Repository
from lxml.etree import (  # type: ignore
    ParseError,
    _Element as lxml_elem,
    _ElementTree as lxml_tree,
    parse as lxml_parse,
)


class CacheError(Exception):
    """
    Custom exception for cache handling errors.
    """


class StatProcessor:
    """
    Main class for fetching and processing GitHub statistics.
    """

    def __init__(self, access_token: str, username: str, birthday: datetime) -> None:
        """
        Initialize all necessary data.
        """

        self.birthday = birthday
        self.just_lengths: dict[str, int] = {
            "age_data_dots": 49,
            "star_data_dots": 50,
            "repo_data_dots": 50,
            "commit_data_dots": 48,
            "loc_total_dots": 40,
        }

        self.cache_dir = Path("cache")
        self.svg_dir = Path("assets")

        self.cache_dir.mkdir(exist_ok=True)
        self.svg_dir.mkdir(exist_ok=True)

        self.gh = Github(auth=Token(access_token))
        self.user = self.gh.get_user()
        self.user_id = self.user.id
        self.verified_emails = self._get_verified_emails()

        self.cache_file: Path = (
            self.cache_dir / f"{sha256(username.encode()).hexdigest()}.json"
        )

        self.repositories: PaginatedList[Repository] = []
        self.star_count: int = 0
        self.repo_count: int = 0
        self.commit_count: int = 0
        self.total_loc_count: int = 0
        self.loc_add_count: int = 0
        self.loc_del_count: int = 0

    def calculate_stats(self) -> None:
        """
        Main entry point for stat calculation.
        """

        self._get_repos_and_stars()
        self._get_loc_data()
        self._get_commit_count()
        self._update_svg("dark_mode.svg")
        self._update_svg("light_mode.svg")

    def _get_verified_emails(self) -> list[str]:
        """
        Fetch all verified email addresses for the user.
        """

        emails: list[str] = []
        try:
            for email_info in self.user.get_emails():
                if email_info.verified:
                    emails.append(email_info.email.lower())
        except GithubException as e:
            print(f"Warning: Could not fetch verified emails: {str(e)}")
        return emails

    def _get_repos_and_stars(self) -> None:
        """
        Get repository count and total star count.
        """

        try:
            repos: PaginatedList[Repository] = self.user.get_repos(type="owner")
            self.repo_count = repos.totalCount
            self.star_count = sum(repo.stargazers_count for repo in repos)
            self.repositories = repos
        except GithubException as e:
            print(f"Failed to get repositories: {str(e)}")

    def _get_loc_data(self) -> None:
        """
        Get lines of code data with caching.
        """

        self.total_loc_count, self.loc_add_count, self.loc_del_count = (
            self._process_cache(self.repositories)
        )

    def _process_cache(
        self, repositories: PaginatedList[Repository]
    ) -> tuple[int, int, int]:
        """
        Process cache and compute LOC totals.
        """

        try:
            with open(self.cache_file, mode="r", encoding="utf-8") as file:
                cache: dict[str, dict[str, int | str]] = load(file)
        except (FileNotFoundError, JSONDecodeError):
            cache: dict[str, dict[str, int | str]] = {}

        loc_add: int = 0
        loc_del: int = 0

        for repo in repositories:
            repo_name: str = repo.full_name
            repo_hash: str = sha256(repo_name.encode()).hexdigest()

            try:
                current_commits: int = repo.get_commits().totalCount
            except GithubException:
                current_commits: int = 0

            if current_commits > 0 and (
                repo_hash not in cache or cache[repo_hash]["commits"] != current_commits
            ):
                try:
                    additions, deletions, user_commits = self._calculate_repo_loc(repo)
                except GithubException as e:
                    print(f"Error processing {repo_name}: {str(e)}")
                    print(f"Setting data for {repo} to 0.")
                    additions = deletions = user_commits = int()
            else:
                cached: dict[str, int | str] = cache.get(repo_hash, {})
                additions = int(cached.get("additions", 0))
                deletions = int(cached.get("deletions", 0))
                user_commits = int(cached.get("user_commits", 0))

            cache[repo_hash] = {
                "name": repo_name,
                "commits": current_commits,
                "user_commits": user_commits,
                "additions": additions,
                "deletions": deletions,
            }

            loc_add += additions
            loc_del += deletions

        try:
            with open(self.cache_file, mode="w", encoding="utf-8") as file:
                dump(cache, file, indent=4, sort_keys=True)
        except IOError as e:
            raise CacheError(f"Failed to write cache: {str(e)}") from e

        return (loc_add - loc_del, loc_add, loc_del)

    def _calculate_repo_loc(self, repo: Repository) -> tuple[int, int, int]:
        """
        Calculate LOC for a single repository.
        """

        additions: int = 0
        deletions: int = 0
        user_commits: int = 0

        try:
            commits: PaginatedList[Commit] = repo.get_commits()
            for commit in commits:
                if self._is_user_commit(commit):
                    additions += commit.stats.additions
                    deletions += commit.stats.deletions
                    user_commits += 1
        except GithubException as e:
            if e.status != 409:
                print(f"Error getting commits for {repo.full_name}: {str(e)}")

        return additions, deletions, user_commits

    def _is_user_commit(self, commit: Commit) -> bool:
        """
        Check if commit belongs to the user using ID or verified emails.
        """

        if (commit.author and commit.author.id == self.user_id) or (
            commit.commit
            and commit.commit.author
            and commit.commit.author.email.lower() in self.verified_emails
        ):
            return True
        return False

    def _get_commit_count(self) -> None:
        """
        Get total commit count from cache.
        """

        try:
            with open(self.cache_file, mode="r", encoding="utf-8") as file:
                cache: dict[str, dict[str, int | str]] = load(file)

            self.commit_count = sum(
                int(repo["user_commits"]) + 1
                if repo["name"] == "jp-zuniga/jp-zuniga"
                else int(repo["user_commits"])
                for repo in cache.values()
            )
        except (FileNotFoundError, JSONDecodeError, KeyError):
            self.commit_count = 0

    def _update_svg(self, svg_name: str) -> None:
        """
        Update SVG file with the new data.
        """

        svg_path: Path = self.svg_dir / svg_name

        try:
            tree: lxml_tree = lxml_parse(svg_path, parser=None)
            root: lxml_elem = tree.getroot()

            self._update_svg_element(root, "age_data", self._calculate_age())
            self._update_svg_element(root, "star_data", self.star_count)
            self._update_svg_element(root, "repo_data", self.repo_count)
            self._update_svg_element(root, "commit_data", self.commit_count)
            self._update_svg_element(root, "loc_total", self.total_loc_count)
            self._update_svg_element(root, "loc_add", self.loc_add_count)
            self._update_svg_element(root, "loc_del", self.loc_del_count)

            tree.write(svg_path, encoding="utf-8", xml_declaration=True)  # type: ignore
        except (IOError, ParseError) as e:
            raise CacheError(f"SVG update failed: {str(e)}") from e

    def _update_svg_element(
        self, root: lxml_elem, element_id: str, value: int | str
    ) -> None:
        """
        Update an SVG element and its corresponding justification dots.
        """

        if isinstance(value, int):
            value_str = f"{value:,}"
        else:
            value_str = str(value)

        if element_id == "loc_add":
            value_str = f"+{value_str}"
        elif element_id == "loc_del":
            value_str = f"−{value_str}"

        value_element: Any = root.find(
            path=f".//*[@id='{element_id}']", namespaces=None
        )

        if value_element is not None:
            value_element.text = value_str

        if element_id in ("loc_add", "loc_del"):
            return

        dots_id = f"{element_id}_dots"
        dots_element: Any = root.find(path=f".//*[@id='{dots_id}']", namespaces=None)

        if dots_element is not None:
            if element_id == "loc_total":
                num_dots: int = self.just_lengths[dots_id] - len(
                    f"{value_str} , +{self.loc_add_count} , −{self.loc_del_count}"
                )
            else:
                num_dots: int = self.just_lengths[dots_id] - len(value_str)

            dots_element.text = f" {'.' * num_dots} "

    def _calculate_age(self) -> str:
        """
        Calculate time since self.birthday.
        """

        diff = relativedelta(datetime.today(), self.birthday)
        return (
            f"{'🎂 ' if (diff.months == 0 and diff.days == 0) else ''}"
            f"{diff.years} year{'s' if diff.years != 1 else ''}, "
            f"{diff.months} month{'s' if diff.months != 1 else ''}, "
            f"{diff.days} day{'s' if diff.days != 1 else ''}"
        )


def main() -> None:
    """
    Fetch GitHub statistics and update SVG files.
    """

    try:
        StatProcessor(
            access_token=environ["ACCESS_TOKEN"],
            username=environ["USER_NAME"],
            birthday=datetime(2005, 7, 7),
        ).calculate_stats()
    except KeyError as e:
        print(f"Missing environment variable: {str(e)}", file=stderr)
        exit(1)
    except (GithubException, CacheError) as e:
        print(f"Error: {str(e)}", file=stderr)
        exit(1)


if __name__ == "__main__":
    main()
