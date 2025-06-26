from datetime import datetime
from hashlib import sha256
from json import JSONDecodeError, dump, load
from os import environ
from pathlib import Path
from sys import exit, stderr
from typing import Any, Union

from dateutil.relativedelta import relativedelta
from github import Github, GithubException
from github.Commit import Commit
from github.Repository import Repository
from lxml.etree import (
    ParseError,
    _Element as lxml_elem,
    _ElementTree as lxml_tree,
    parse as lxml_parse,
)


class GitHubAPIError(Exception):
    """
    Custom exception for GitHub API errors.
    """

    pass


class CacheError(Exception):
    """
    Custom exception for cache handling errors.
    """

    pass


class StatProcessor:
    """
    Main class for fetching and processing GitHub statistics.
    """

    def __init__(self, access_token: str, username: str, birthday: datetime) -> None:
        """
        Initialize all necessary data.
        """

        self.just_lengths: dict[str, int] = {
            "age_data_dots": 55,
            "star_data_dots": 56,
            "repo_data_dots": 56,
            "commit_data_dots": 54,
            "loc_total_dots": 46,
        }

        self.cache_dir = Path("cache")
        self.svg_dir = Path("assets")

        self.cache_dir.mkdir(exist_ok=True)
        self.svg_dir.mkdir(exist_ok=True)

        self.access_token = access_token
        self.username = username
        self.birthday = birthday

        self.gh = Github(access_token)
        self.user = self.gh.get_user(username)
        self.user_id = self.user.id

        self.cache_file: Path = (
            self.cache_dir / f"{sha256(username.encode()).hexdigest()}.json"
        )

        self.stars: int = 0
        self.repos: int = 0
        self.commits: int = 0
        self.loc_total: int = 0
        self.loc_add: int = 0
        self.loc_del: int = 0

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

    def _get_repos_and_stars(self) -> None:
        """
        Get repository count and total star count.
        """

        try:
            repos = list(self.user.get_repos(affiliation="owner"))
            self.repos = len(repos)
            self.stars = sum(repo.stargazers_count for repo in repos)
            self.repositories = repos
        except GithubException as e:
            raise GitHubAPIError(f"Failed to get repositories: {str(e)}") from e

    def _get_loc_data(self) -> None:
        """
        Get lines of code data with caching.
        """

        self.loc_total, self.loc_add, self.loc_del = self._process_cache(
            self.repositories
        )

    def _process_cache(self, repositories: list[Repository]) -> tuple[int, int, int]:
        """
        Process cache and compute LOC totals.
        """

        try:
            with open(self.cache_file, "r") as f:
                cache: dict[str, dict[str, Union[int, str]]] = load(f)
        except (FileNotFoundError, JSONDecodeError):
            cache = {}

        loc_add: int = 0
        loc_del: int = 0

        for repo in repositories:
            repo_name = repo.full_name
            repo_hash = sha256(repo_name.encode()).hexdigest()

            try:
                current_commits = repo.get_commits().totalCount
            except GithubException:
                current_commits = 0

            if current_commits > 0 and (
                repo_hash not in cache or cache[repo_hash]["commits"] != current_commits
            ):
                try:
                    additions, deletions, user_commits = self._calculate_repo_loc(repo)
                except Exception as e:
                    print(f"Error processing {repo_name}: {str(e)}")
                    additions, deletions, user_commits = 0, 0, 0
            else:
                cached = cache.get(repo_hash, {})
                additions = cached.get("additions", 0)
                deletions = cached.get("deletions", 0)
                user_commits = cached.get("user_commits", 0)
            # Update cache
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
            with open(self.cache_file, "w") as f:
                dump(cache, f, indent=4)
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
            commits = repo.get_commits()
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
        Check if commit belongs to the user.
        """

        if commit.author:
            return commit.author.id == self.user_id
        return False

    def _get_commit_count(self) -> None:
        """
        Get total commit count from cache.
        """

        try:
            with open(self.cache_file, "r") as f:
                cache: dict[str, dict[str, Union[int, str]]] = load(f)
            self.commits = sum(int(repo["user_commits"]) for repo in cache.values())
        except (FileNotFoundError, JSONDecodeError, KeyError):
            self.commits = 0

    def _update_svg(self, svg_name: str) -> None:
        """
        Update SVG file with the new data.
        """

        svg_path: Path = self.svg_dir / svg_name

        try:
            tree: lxml_tree = lxml_parse(svg_path, parser=None)
            root: lxml_elem = tree.getroot()

            self._update_svg_element(root, "age_data", self._calculate_age())
            self._update_svg_element(root, "star_data", self.stars)
            self._update_svg_element(root, "repo_data", self.repos)
            self._update_svg_element(root, "commit_data", self.commits)
            self._update_svg_element(root, "loc_total", self.loc_total)
            self._update_svg_element(root, "loc_add", self.loc_add)
            self._update_svg_element(root, "loc_del", self.loc_del)

            tree.write(svg_path, encoding="utf-8", xml_declaration=True)  # type: ignore
        except (IOError, ParseError) as e:
            raise CacheError(f"SVG update failed: {str(e)}") from e

    def _update_svg_element(
        self, root: lxml_elem, element_id: str, value: Union[int, str]
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
            value_str = f"-{value_str}"

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
                    f"{value_str} , +{self.loc_add} , -{self.loc_del}"
                )
            else:
                num_dots: int = self.just_lengths[dots_id] - len(value_str)

            dots_element.text = f" {'.' * num_dots} "

    def calculate_stats(self) -> None:
        """
        Main entry point for stat calculation.
        """

        self._get_repos_and_stars()
        self._get_loc_data()
        self._get_commit_count()

        self._update_svg("dark_mode.svg")
        self._update_svg("light_mode.svg")


def main() -> None:
    """
    Fetch GitHub statistics and update SVG files.
    """

    try:
        StatProcessor(
            access_token=environ["GH_TOKEN"],
            username=environ["USER_NAME"],
            birthday=datetime(2005, 7, 7),
        ).calculate_stats()
    except KeyError as e:
        print(f"Missing environment variable: {str(e)}", file=stderr)
        exit(1)
    except (GitHubAPIError, CacheError) as e:
        print(f"Error: {str(e)}", file=stderr)
        exit(1)


if __name__ == "__main__":
    main()
