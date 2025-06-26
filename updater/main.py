from datetime import datetime
from hashlib import sha256
from json import JSONDecodeError, dump, load
from os import environ
from pathlib import Path
from sys import exit, stderr
from typing import Any, Union

from dateutil.relativedelta import relativedelta
from lxml.etree import (
    ParseError,
    _Element as lxml_elem,
    _ElementTree as lxml_tree,
    parse as lxml_parse,
)
from requests import RequestException, Response, post


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

    API_ENDPOINT: str = "https://api.github.com/graphql"
    CACHE_DIR = Path("cache")
    SVG_DIR = Path("assets")

    DOTS_LENGTHS: dict[str, int] = {
        "age_data_dots": 55,
        "star_data_dots": 56,
        "repo_data_dots": 56,
        "commit_data_dots": 54,
        "loc_total_dots": 46,
    }

    QUERIES: dict[str, str] = {
        "user": """
            query($login: String!){
                user(login: $login) {
                    id
                    createdAt
                }
            }
        """,
        "repos": """
            query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
                user(login: $login) {
                    repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                        totalCount
                        edges {
                            node {
                                ... on Repository {
                                    nameWithOwner
                                    stargazers {
                                        totalCount
                                    }
                                }
                            }
                        }
                        pageInfo {
                            endCursor
                            hasNextPage
                        }
                    }
                }
            }
        """,
        "repo_history": """
            query ($repo_name: String!, $owner: String!, $cursor: String) {
                repository(name: $repo_name, owner: $owner) {
                    defaultBranchRef {
                        target {
                            ... on Commit {
                                history(first: 100, after: $cursor) {
                                    totalCount
                                    edges {
                                        node {
                                            ... on Commit {
                                                author {
                                                    user {
                                                        id
                                                    }
                                                }
                                                deletions
                                                additions
                                            }
                                        }
                                    }
                                    pageInfo {
                                        endCursor
                                        hasNextPage
                                    }
                                }
                            }
                        }
                    }
                }
            }
        """,
        "loc_query": """
            query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
                user(login: $login) {
                    repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
                        edges {
                            node {
                                ... on Repository {
                                    nameWithOwner
                                    defaultBranchRef {
                                        target {
                                            ... on Commit {
                                                history {
                                                    totalCount
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        pageInfo {
                            endCursor
                            hasNextPage
                        }
                    }
                }
            }
        """,
    }

    def __init__(self, access_token: str, username: str, birthday: datetime) -> None:
        """
        Initialize all necessary data.
        """

        self.CACHE_DIR.mkdir(exist_ok=True)
        self.SVG_DIR.mkdir(exist_ok=True)

        self.access_token = access_token
        self.username = username
        self.birthday = birthday

        self.headers: dict[str, str] = {"authorization": f"token {access_token}"}
        self.user_id = self._get_user_id()

        self.cache_file: Path = (
            self.CACHE_DIR / f"{sha256(username.encode()).hexdigest()}.json"
        )

        self.stars: int = 0
        self.repos: int = 0
        self.commits: int = 0
        self.loc_total: int = 0
        self.loc_add: int = 0
        self.loc_del: int = 0

    def _get_user_id(self) -> str:
        """
        Fetch self.username's Github user ID.
        """

        query: str = self.QUERIES["user"]
        variables: dict[str, str] = {"login": self.username}
        data: dict = self._send_request(query, variables)

        return data["data"]["user"]["id"]

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

    def _send_request(self, query: str, variables: dict[str, str]) -> dict[str, Any]:
        """
        Make a GraphQL request and raise exceptions if necessary.
        """

        try:
            response: Response = post(
                self.API_ENDPOINT,
                json={"query": query, "variables": variables},
                headers=self.headers,
                timeout=10,
            )

            response.raise_for_status()
            return response.json()
        except RequestException as e:
            raise GitHubAPIError(f"Request failed: {str(e)}") from e

    def _get_repos_or_stars(
        self, owner_affiliation: list[str], count_type: str
    ) -> None:
        """
        Get repository count or total star count with pagination.
        """

        total: int = 0
        cursor: Any = None
        has_next_page: Any = True

        while has_next_page:
            variables: dict[str, Any] = {
                "owner_affiliation": owner_affiliation,
                "login": self.username,
                "cursor": cursor,
            }

            data: dict[str, Any] = self._send_request(self.QUERIES["repos"], variables)
            repos: Any = data["data"]["user"]["repositories"]

            if count_type == "repos":
                self.repos = repos["totalCount"]
                return
            elif count_type == "stars":
                total += sum(
                    edge["node"]["stargazers"]["totalCount"] for edge in repos["edges"]
                )

            page_info: Any = repos["pageInfo"]
            has_next_page: Any = page_info["hasNextPage"]
            cursor: Any = page_info["endCursor"]

        self.stars = total

    def _get_loc_data(self, owner_affiliation: list[str]) -> None:
        """
        Get lines of code data with caching.
        """

        edges: list[Any] = []
        cursor: Any = None
        has_next_page: Any = True

        while has_next_page:
            variables: dict[str, Any] = {
                "owner_affiliation": owner_affiliation,
                "login": self.username,
                "cursor": cursor,
            }

            data: dict[str, Any] = self._send_request(
                self.QUERIES["loc_query"], variables
            )

            repos: Any = data["data"]["user"]["repositories"]
            edges.extend(repos["edges"])

            page_info: Any = repos["pageInfo"]
            has_next_page: Any = page_info["hasNextPage"]
            cursor: Any = page_info["endCursor"]

        self.loc_total, self.loc_add, self.loc_del = self._process_cache(edges)

    def _process_cache(self, edges: list[dict[str, Any]]) -> tuple[int, int, int]:
        """
        Process cache and compute LOC totals.
        """

        try:
            with open(self.cache_file, "r") as f:
                cache: dict[str, dict[str, Union[int, str]]] = load(f)
        except (FileNotFoundError, JSONDecodeError):
            cache: dict[str, dict[str, Union[int, str]]] = {}

        loc_add: int = 0
        loc_del: int = 0

        for edge in edges:
            repo: Any = edge.get("node", {})
            repo_name: Any = repo.get("nameWithOwner")
            if not repo_name:
                continue

            repo_hash: str = sha256(repo_name.encode()).hexdigest()
            default_branch: Any = repo.get("defaultBranchRef", {})
            target: Any = default_branch.get("target", {}) if default_branch else {}
            history: Any = target.get("history", {}) if target else {}
            current_commits: Any = history.get("totalCount", 0)

            if current_commits > 0:
                owner, name = repo_name.split("/")
                try:
                    additions, deletions, user_commits = self._calculate_repo_loc(
                        owner, name
                    )
                except Exception as e:
                    print(f"Error processing {repo_name}: {str(e)}")
                    additions, deletions, user_commits = 0, 0, 0
            else:
                additions, deletions, user_commits = 0, 0, 0

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

    def _calculate_repo_loc(self, owner: str, repo_name: str) -> tuple[int, int, int]:
        """
        Calculate LOC for a single repository.
        """

        additions: int = 0
        deletions: int = 0
        user_commits: int = 0
        cursor: Any = None
        has_next: Any = True

        while has_next:
            variables: dict[str, Any] = {
                "owner": owner,
                "repo_name": repo_name,
                "cursor": cursor,
            }

            try:
                data: dict[str, Any] = self._send_request(
                    self.QUERIES["repo_history"], variables
                )
            except GitHubAPIError:
                break

            repo_data: Any = data.get("data", {}).get("repository")
            if not repo_data or not repo_data.get("defaultBranchRef"):
                break

            history: Any = repo_data["defaultBranchRef"]["target"]["history"]
            total_commits: Any = history["totalCount"]

            for edge in history.get("edges", []):
                commit: Any = edge.get("node", {})
                author: Any = commit.get("author", {})
                user: Any = author.get("user", {}) if author else {}

                if user and user.get("id") == self.user_id:
                    additions += commit.get("additions", 0)
                    deletions += commit.get("deletions", 0)
                    user_commits += 1

            page_info: Any = history.get("pageInfo", {})
            has_next: Any = (
                page_info.get("hasNextPage", False) and user_commits < total_commits
            )

            cursor: Any = page_info.get("endCursor")

        return additions, deletions, user_commits

    def _get_commit_count(self) -> None:
        """
        Get total commit count from cache.
        """

        try:
            with open(self.cache_file, "r") as f:
                cache: dict[str, dict[str, Union[int, str]]] = load(f)
            self.commits = sum([int(repo["user_commits"]) for repo in cache.values()])
        except (FileNotFoundError, JSONDecodeError, KeyError):
            self.commits = 0

    def _update_svg(self, svg_name: str) -> None:
        """
        Update SVG file with the new data.
        """

        svg_path: Path = self.SVG_DIR / svg_name

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
                num_dots: int = self.DOTS_LENGTHS[dots_id] - len(
                    f"{value_str} , +{self.loc_add} , -{self.loc_del}"
                )
            else:
                num_dots: int = self.DOTS_LENGTHS[dots_id] - len(value_str)

            dots_element.text = f" {'.' * num_dots} "

    def calculate_stats(self) -> None:
        """
        Main entry point for stat calculation.
        """

        self._get_repos_or_stars(["OWNER"], "stars")
        self._get_repos_or_stars(["OWNER"], "repos")
        self._get_loc_data(["OWNER"])
        self._get_commit_count()

        self._update_svg("dark_mode.svg")
        self._update_svg("light_mode.svg")


def main() -> None:
    """
    Fetch personal user data from Github's GraphQL4 API,
    and update the README's SVG image with the new data.
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
